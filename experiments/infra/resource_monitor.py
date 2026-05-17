"""Background resource monitor: Docker container stats + ICMP RTT probes.

RTT targets are configured dynamically from IPC lab_ready events emitted by labs.
ResourceMonitor always runs (CPU/RAM/disk/RTT); capture and IDS are toggleable separately.

Lifecycle::

    monitor = ResourceMonitor(
        scenario_config=ScenarioRttConfig(),  # Start empty
        sample_interval_sec=1.0,
    )
    #monitor.collect_baseline(n_samples=5)   # synchronous, before attack
    #monitor.start_attack_phase()            # samples while scenario-runner executes
    # ... IPC events received ...
    ipc_rtt_cfg = rtt_config_from_ipc_events(events, scenario_id)
    monitor.apply_runtime_rtt_config(ipc_rtt_cfg)  # Apply IPC RTT config
    # ... run lab and attack via scenario-runner ...
    monitor.stop()                          # stops background thread
    monitor.save(Path("resource_metrics.json"), ipc_events)
"""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import docker
import psutil
from pydantic import BaseModel, Field
from experiments.core import logger


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _attack_windows_from_ipc(events: list[dict[str, Any]]) -> list[tuple[datetime, datetime]]:
    starts: dict[tuple[object, object, object], datetime] = {}
    windows: list[tuple[datetime, datetime]] = []

    for event in events:
        state = event.get("state")
        ts = _parse_utc(event.get("ts_utc"))
        if ts is None:
            continue
        key = (event.get("stack"), event.get("scenario"), event.get("instance"))
        if state == "attack_start":
            starts[key] = ts
        elif state == "attack_end" and key in starts:
            windows.append((starts.pop(key), ts))

    return windows


def _indices_inside_windows(
    timestamps_utc: list[str], windows: list[tuple[datetime, datetime]]
) -> list[int]:
    if not windows:
        return list(range(len(timestamps_utc)))

    indices: list[int] = []
    for index, raw_ts in enumerate(timestamps_utc):
        ts = _parse_utc(raw_ts)
        if ts is not None and any(start <= ts <= end for start, end in windows):
            indices.append(index)
    return indices


def _pick(values: list[Any], indices: list[int]) -> list[Any]:
    return [values[index] for index in indices if index < len(values)]


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


class RttTargetConfig(BaseModel):
    service: str = ""
    label: str | None = None
    protocol: str = "icmp"
    host: str | None = None
    port: int | None = None


class ScenarioRttConfig(BaseModel):
    stack_id: str = ""
    rtt_targets: list[RttTargetConfig] = Field(default_factory=list)


def _as_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def rtt_config_from_ipc_events(
    events: list[dict[str, Any]],
    scenario_id: int,
    stack_id: str = "",
) -> ScenarioRttConfig:
    """Build RTT target config from scenario-runner IPC events.

    Supported fields inside an IPC event:
    - ``rtt_service`` or ``service``
    - ``rtt_host`` or ``rtt_ip`` or ``host``
    - ``rtt_port`` or ``port``
    - ``rtt_protocol`` or ``protocol``
    - ``rtt_label`` or ``label``
    """
    targets: list[RttTargetConfig] = []
    seen: set[tuple[str, str, int | None, str, str]] = set()

    for event in events:
        if not isinstance(event, dict):
            continue

        event_scenario = _as_int(event.get("scenario"))
        if event_scenario is not None and event_scenario != scenario_id:
            continue

        event_stack = event.get("stack")
        if stack_id and isinstance(event_stack, str) and event_stack and event_stack != stack_id:
            continue

        service = str(event.get("rtt_service") or event.get("service") or "").strip()
        host = str(event.get("rtt_host") or event.get("rtt_ip") or event.get("host") or "").strip()
        label = str(event.get("rtt_label") or event.get("label") or "").strip() or None
        port = _as_int(event.get("rtt_port"))
        if port is None:
            port = _as_int(event.get("port"))

        protocol_raw = str(event.get("rtt_protocol") or event.get("protocol") or "").strip().lower()
        protocol = protocol_raw or ("tcp" if port is not None else "icmp")

        # Change rationale: accept RTT target hints only when at least a service or an IP/host is provided.
        if not service and not host:
            continue
        if protocol == "tcp" and port is None:
            continue

        target = RttTargetConfig(
            service=service,
            label=label,
            protocol=protocol,
            host=host or None,
            port=port,
        )
        dedupe_key = (
            target.protocol,
            target.host or "",
            target.port,
            target.service,
            target.label or "",
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        targets.append(target)

    return ScenarioRttConfig(stack_id=stack_id, rtt_targets=targets)


def resolve_rtt_probes(
    client: docker.DockerClient, stack_id: str, targets: list[RttTargetConfig]
) -> List[dict]:
    """Discover running container instances for each target service and return
    a flat list of probe dicts: {label, container_name, host (IP)}.

    Uses Docker labels ``com.docker.compose.project`` and
    ``com.docker.compose.service`` to find all instances, so N parallel
    instances of the same scenario are all probed automatically.
    """
    probes: List[dict] = []
    for target in targets:
        protocol = (target.protocol or "icmp").lower()
        base_label = target.label or target.service or target.host or "probe"
        if target.host:
            probe: dict[str, object] = {
                "label": base_label,
                "container_name": "",
                "host": target.host,
                "protocol": protocol,
            }
            if target.port is not None:
                probe["port"] = target.port
            probes.append(probe)
            continue

        service = target.service
        if not service:
            continue
        containers = client.containers.list(filters={"label": f"com.docker.compose.service={service}"})
        for container in containers:
            project = container.labels.get("com.docker.compose.project", "")
            # Accept containers whose project is the exact stack_id or any instance suffix
            if project != stack_id and not project.startswith(stack_id + "_"):
                continue
            ip = _first_container_ip(container)
            if ip:
                # Include instance identifier in label when multiple instances exist
                instance_suffix = project[len(stack_id):]  # "" for default, "_2" for instance 2
                probe_label = (
                    f"{base_label}{instance_suffix}" if instance_suffix else base_label
                )
                probe = {
                    "label": probe_label,
                    "container_name": container.name,
                    "host": ip,
                    "protocol": protocol,
                }
                if target.port is not None:
                    probe["port"] = target.port
                probes.append(probe)
    return probes


def _first_container_ip(container: docker.models.containers.Container) -> Optional[str]:
    """Return the first non-empty IP address from a container's network settings."""
    try:
        networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
        for details in networks.values():
            ip = details.get("IPAddress", "").strip()
            if ip:
                return ip
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Low-level samplers
# ---------------------------------------------------------------------------


def _docker_all_stats(client: docker.DockerClient) -> Dict[str, dict]:
    """Snapshot Docker stats for all running containers. Best-effort, parallelized."""
    import concurrent.futures
    
    result: Dict[str, dict] = {}
    
    try:
        containers = client.containers.list()
    except Exception:
        return result
    
    if not containers:
        return result
    
    def _get_stats(container):
        try:
            return (container.name, container.stats(stream=False))
        except Exception:
            return (container.name, None)
    
    # Collect stats in parallel with reasonable timeout
    # Change rationale: parallel collection reduces total time from N*1s to ~1.5s for N containers
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(_get_stats, c): c for c in containers}
            try:
                for future in concurrent.futures.as_completed(futures, timeout=3.0):
                    try:
                        name, stats = future.result(timeout=0.2)
                        if stats is not None:
                            result[name] = stats
                    except (concurrent.futures.TimeoutError, Exception):
                        # Skip containers that timeout or fail
                        pass
            except concurrent.futures.TimeoutError:
                # Some containers didn't complete in time; return partial results
                pass
    except Exception:
        # If anything goes wrong, return empty or partial results
        pass
    
    return result


def _parse_cpu_mem_disk(stats: dict) -> tuple[float, float, float]:
    """Extract (cpu_pct, mem_mb, disk_cumulative_bytes) from a Docker stats snapshot."""
    cpu_delta = (
        stats["cpu_stats"]["cpu_usage"].get("total_usage", 0)
        - stats["precpu_stats"]["cpu_usage"].get("total_usage", 0)
    )
    system_delta = (
        stats["cpu_stats"].get("system_cpu_usage", 0)
        - stats["precpu_stats"].get("system_cpu_usage", 0)
    )
    cpus = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", []) or [1])
    cpu_pct = ((cpu_delta / system_delta) * cpus * 100.0) if system_delta > 0 else 0.0
    mem_mb = stats["memory_stats"].get("usage", 0) / (1024 * 1024)
    disk_bytes = sum(
        float(item.get("value", 0))
        for item in (stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []) or [])
        if str(item.get("op", "")).lower() in {"read", "write"}
    )
    return cpu_pct, mem_mb, disk_bytes


def _ping_once(host: str) -> tuple[float, float]:
    """Return (rtt_ms, packet_loss_pct) from a single ICMP ping. Returns (-1, 100) on failure."""
    try:
        from ping3 import ping

        # Change rationale: use ping3 instead of parsing platform-specific ping output.
        rtt_sec = ping(host, timeout=1, unit="s")
        if rtt_sec is None or rtt_sec is False:
            return -1.0, 100.0
        return float(rtt_sec) * 1000.0, 0.0
    except Exception:
        return -1.0, 100.0


def _tcp_probe_once(host: str, port: int) -> tuple[float, float]:
    """Return (rtt_ms, packet_loss_pct) from one TCP connect probe."""
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        return -1.0, 100.0
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, 0.0


def _probe_once(probe: dict) -> tuple[float, float]:
    protocol = str(probe.get("protocol", "icmp")).lower()
    host = str(probe.get("host", ""))
    if protocol == "tcp":
        port_raw = probe.get("port")
        port = int(port_raw) if isinstance(port_raw, int) else _as_int(port_raw)
        if port is None:
            return -1.0, 100.0
        return _tcp_probe_once(host, port)
    return _ping_once(host)


# ---------------------------------------------------------------------------
# ResourceMonitor
# ---------------------------------------------------------------------------


def _avg(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cumul_to_rates(cumul: List[float], interval: float) -> List[float]:
    return [max(cumul[i] - cumul[i - 1], 0.0) / interval for i in range(1, len(cumul))]


def _summarize(samples: List[float]) -> dict:
    return {"avg": _avg(samples), "peak": max(samples) if samples else 0.0, "samples": samples}


class ResourceMonitor:
    """Samples Docker container CPU/RAM/disk and ICMP RTT probes in a background thread.

    RTT targets are resolved at construction time via Docker service labels so
    all running instances of the scenario (single or multi) are covered.

    Separates a baseline phase from the real attack phase marked by IPC.
    """

    def __init__(
        self,
        scenario_config: ScenarioRttConfig | dict,
        sample_interval_sec: float = 1.0,
    ) -> None:
        self._interval = sample_interval_sec
        self._client = docker.from_env()
        self._stop_event = threading.Event()
        self._probe_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        config = (
            ScenarioRttConfig.model_validate(scenario_config)
            if isinstance(scenario_config, dict)
            else scenario_config
        )

        # Resolve RTT probes: one entry per running container instance
        stack_id = config.stack_id
        raw_targets = config.rtt_targets
        self._probes: List[dict] = (
            resolve_rtt_probes(self._client, stack_id, raw_targets)
            if stack_id and raw_targets
            else []
        )

        # Storage: {container_name: {cpu: [], mem_mb: [], disk_cumul: []}}
        self._baseline_containers: Dict[str, Dict[str, List[float]]] = {}
        self._baseline_host: Dict[str, List[float]] = {"cpu": [], "mem_pct": [], "mem_mb": []}
        self._baseline_rtt: Dict[str, List[dict]] = {p["label"]: [] for p in self._probes}
        self._baseline_timestamps: List[float] = []
        self._baseline_utc: List[str] = []

        self._attack_containers: Dict[str, Dict[str, List[float]]] = {}
        self._attack_host: Dict[str, List[float]] = {"cpu": [], "mem_pct": [], "mem_mb": []}
        self._attack_rtt: Dict[str, List[dict]] = {p["label"]: [] for p in self._probes}
        self._attack_timestamps: List[float] = []
        self._attack_utc: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect_baseline(self, n_samples: int) -> None:
        """Collect n_samples baseline snapshots synchronously (before attack)."""
        t0 = time.perf_counter()
        for _ in range(n_samples):
            self._baseline_timestamps.append(time.perf_counter() - t0)
            self._baseline_utc.append(utc_now_iso())
            self._snapshot_host(self._baseline_host)
            self._snapshot_containers(self._baseline_containers, len(self._baseline_timestamps))
            self._snapshot_rtt(self._baseline_rtt)
            time.sleep(self._interval)

    def start_attack_phase(self) -> None:
        """Start background sampling. Call immediately before launching the attack."""
        t0 = time.perf_counter()
        self._stop_event.clear()

        def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self._attack_timestamps.append(time.perf_counter() - t0)
                    self._attack_utc.append(utc_now_iso())
                    self._snapshot_host(self._attack_host)
                    self._snapshot_containers(self._attack_containers, len(self._attack_timestamps))
                    self._snapshot_rtt(self._attack_rtt)
                except Exception:
                    logger.error("Error occurred while sampling")
                    # Continue sampling even if one snapshot fails
                    pass
                time.sleep(self._interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop attack-phase background sampling."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def apply_runtime_rtt_config(self, scenario_config: ScenarioRttConfig | dict) -> None:
        """Apply RTT target changes while sampling is running.

        The new configuration replaces current probes and keeps old collected
        samples untouched.
        """
        config = (
            ScenarioRttConfig.model_validate(scenario_config)
            if isinstance(scenario_config, dict)
            else scenario_config
        )
        new_probes = (
            resolve_rtt_probes(self._client, config.stack_id, config.rtt_targets)
            if config.rtt_targets
            else []
        )
        with self._probe_lock:
            self._probes = new_probes
            for probe in new_probes:
                label = str(probe.get("label", ""))
                if not label:
                    continue
                self._baseline_rtt.setdefault(label, [])
                self._attack_rtt.setdefault(label, [])

    def save(self, path: Path, ipc_events: list[dict[str, Any]] | None = None) -> None:
        """Serialize collected metrics to a JSON file."""
        path.write_text(json.dumps(self._build_payload(ipc_events or []), indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Internal: snapshot helpers
    # ------------------------------------------------------------------

    def _snapshot_containers(
        self, store: Dict[str, Dict[str, List[float]]], sample_count: int
    ) -> None:
        stats_by_name = _docker_all_stats(self._client)
        for name in set(store) | set(stats_by_name):
            if name not in store:
                # Change rationale: keep container samples aligned with phase timestamps.
                store[name] = {
                    "cpu": [0.0] * (sample_count - 1),
                    "mem_mb": [0.0] * (sample_count - 1),
                    "disk_cumul": [0.0] * (sample_count - 1),
                }
            if name in stats_by_name:
                cpu, mem, disk = _parse_cpu_mem_disk(stats_by_name[name])
            else:
                cpu, mem, disk = 0.0, 0.0, 0.0
            store[name]["cpu"].append(cpu)
            store[name]["mem_mb"].append(mem)
            store[name]["disk_cumul"].append(disk)

    def _snapshot_host(self, store: Dict[str, List[float]]) -> None:
        memory = psutil.virtual_memory()
        store["cpu"].append(float(psutil.cpu_percent(interval=None)))
        store["mem_pct"].append(float(memory.percent))
        store["mem_mb"].append(float(memory.used) / (1024 * 1024))

    def _snapshot_rtt(self, store: Dict[str, List[dict]]) -> None:
        with self._probe_lock:
            probes = list(self._probes)
        for probe in probes:
            rtt, loss = _probe_once(probe)
            store.setdefault(probe["label"], []).append(
                {"rtt_ms": rtt, "packet_loss_pct": loss}
            )

    # ------------------------------------------------------------------
    # Internal: payload builder
    # ------------------------------------------------------------------

    def _build_payload(self, ipc_events: list[dict[str, Any]]) -> dict:
        attack_windows = _attack_windows_from_ipc(ipc_events)
        attack_indices = _indices_inside_windows(self._attack_utc, attack_windows)
        with self._probe_lock:
            current_probes = list(self._probes)
        # Change rationale: scenario-runner starts before the actual exploit; IPC marks the real attack window.
        attack_containers = _filter_container_store(self._attack_containers, attack_indices)
        attack_host = _filter_series_store(self._attack_host, attack_indices)
        attack_rtt = _filter_rtt_store(self._attack_rtt, attack_indices)
        attack_timestamps = _pick(self._attack_timestamps, attack_indices)
        attack_utc = _pick(self._attack_utc, attack_indices)

        def container_metrics(
            baseline: Dict[str, Dict[str, List[float]]],
            attack: Dict[str, Dict[str, List[float]]],
        ) -> dict:
            out: dict = {}
            for name in set(baseline) | set(attack):
                b = baseline.get(name, {"cpu": [], "mem_mb": [], "disk_cumul": []})
                a = attack.get(name, {"cpu": [], "mem_mb": [], "disk_cumul": []})
                out[name] = {
                    "baseline": {
                        "cpu_pct": _summarize(b["cpu"]),
                        "mem_mb": _summarize(b["mem_mb"]),
                        "disk_io_bps": _summarize(_cumul_to_rates(b["disk_cumul"], self._interval)),
                    },
                    "attack": {
                        "cpu_pct": _summarize(a["cpu"]),
                        "mem_mb": _summarize(a["mem_mb"]),
                        "disk_io_bps": _summarize(_cumul_to_rates(a["disk_cumul"], self._interval)),
                    },
                }
            return out

        def rtt_metrics(
            baseline: Dict[str, List[dict]],
            attack: Dict[str, List[dict]],
        ) -> dict:
            out: dict = {}
            with self._probe_lock:
                probes = list(self._probes)
            for probe in probes:
                label = probe["label"]
                b_rtts = [s["rtt_ms"] for s in baseline.get(label, []) if s["rtt_ms"] >= 0]
                a_rtts = [s["rtt_ms"] for s in attack.get(label, []) if s["rtt_ms"] >= 0]
                b_loss = [s["packet_loss_pct"] for s in baseline.get(label, [])]
                a_loss = [s["packet_loss_pct"] for s in attack.get(label, [])]
                out[label] = {
                    "host": probe["host"],
                    "container_name": probe["container_name"],
                    "protocol": probe.get("protocol", "icmp"),
                    "port": probe.get("port"),
                    "baseline": {
                        "rtt_ms": _summarize(b_rtts),
                        "packet_loss_pct": _summarize(b_loss),
                    },
                    "attack": {
                        "rtt_ms": _summarize(a_rtts),
                        "packet_loss_pct": _summarize(a_loss),
                    },
                }
            return out

        return {
            "sample_interval_sec": self._interval,
            "resolved_probes": current_probes,
            "phase_source": "ipc" if attack_windows else "legacy_runner_window",
            "attack_windows_utc": [
                {
                    "start_utc": start.isoformat().replace("+00:00", "Z"),
                    "end_utc": end.isoformat().replace("+00:00", "Z"),
                }
                for start, end in attack_windows
            ],
            "baseline_timestamps_sec": self._baseline_timestamps,
            "baseline_timestamps_utc": self._baseline_utc,
            "attack_timestamps_sec": attack_timestamps,
            "attack_timestamps_utc": attack_utc,
            "run_timestamps_sec": self._attack_timestamps,
            "run_timestamps_utc": self._attack_utc,
            "host": {
                "baseline": {
                    "cpu_pct": _summarize(self._baseline_host["cpu"]),
                    "mem_pct": _summarize(self._baseline_host["mem_pct"]),
                    "mem_mb": _summarize(self._baseline_host["mem_mb"]),
                },
                "attack": {
                    "cpu_pct": _summarize(attack_host["cpu"]),
                    "mem_pct": _summarize(attack_host["mem_pct"]),
                    "mem_mb": _summarize(attack_host["mem_mb"]),
                },
            },
            "containers": container_metrics(self._baseline_containers, attack_containers),
            "rtt_probes": rtt_metrics(self._baseline_rtt, attack_rtt),
        }


def _filter_series_store(
    store: Dict[str, List[float]], indices: list[int]
) -> Dict[str, List[float]]:
    return {name: _pick(values, indices) for name, values in store.items()}


def _filter_container_store(
    store: Dict[str, Dict[str, List[float]]], indices: list[int]
) -> Dict[str, Dict[str, List[float]]]:
    return {
        name: {metric: _pick(values, indices) for metric, values in metrics.items()}
        for name, metrics in store.items()
    }


def _filter_rtt_store(
    store: Dict[str, List[dict]], indices: list[int]
) -> Dict[str, List[dict]]:
    return {name: _pick(values, indices) for name, values in store.items()}
