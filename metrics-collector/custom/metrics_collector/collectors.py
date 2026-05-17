from __future__ import annotations

import json
import re
import shlex
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import docker
from docker.models.containers import Container

from .models import BuildTiming, DeploymentMetric, NetworkMetric, ResourceMetric, StackInfo
from .utils import log_flow, mean, parse_cpu_percent, parse_mem_usage_mb, run_cmd, timed_cmd

PING_TIME_RE = re.compile(r"time=([0-9.]+)")
PING_LOSS_RE = re.compile(r"([0-9.]+)% packet loss")
NMAP_HOST_LATENCY_RE = re.compile(r"Host is up \(([0-9.]+)s latency\)")
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def _extract_cpu_mem_disk(stats: dict) -> tuple[float, float, float]:
    cpu_delta = stats["cpu_stats"]["cpu_usage"].get("total_usage", 0) - stats["precpu_stats"]["cpu_usage"].get("total_usage", 0)
    system_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - stats["precpu_stats"].get("system_cpu_usage", 0)
    cpus = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", []) or [1])
    cpu_pct = ((cpu_delta / system_delta) * cpus * 100.0) if system_delta > 0 else 0.0
    mem_mb = stats["memory_stats"].get("usage", 0) / (1024 * 1024)

    blkio_total_bytes = 0.0
    for item in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []) or []:
        op = str(item.get("op", "")).lower()
        if op in {"read", "write"}:
            blkio_total_bytes += float(item.get("value", 0))

    return cpu_pct, mem_mb, blkio_total_bytes


def _rates_from_cumulative(samples: List[float], sample_interval_sec: float) -> List[float]:
    if len(samples) < 2:
        return []
    rates: List[float] = []
    for idx in range(1, len(samples)):
        delta = samples[idx] - samples[idx - 1]
        rates.append(max(delta, 0.0) / sample_interval_sec)
    return rates


def _timed_make_target(
    stack_path: Path,
    target: str,
    service: Optional[str] = None,
    required: bool = True,
) -> tuple[float, object]:
    cmd = ["make", target]
    if service:
        cmd.append(f"SERVICE={service}")
    log_flow(f"Executing make target: {' '.join(cmd)} (cwd={stack_path})")
    duration, proc = timed_cmd(cmd, cwd=stack_path, check=False)
    log_flow(
        f"Completed make target: {' '.join(cmd)} "
        f"(returncode={proc.returncode}, duration_sec={duration:.3f})"
    )
    if required and proc.returncode != 0:
        log_flow(f"Required make target failed: {' '.join(cmd)}")
        raise RuntimeError(
            f"Command failed in stack '{stack_path}': {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return duration, proc


def _run_make_target(
    stack_path: Path,
    target: str,
    service: Optional[str] = None,
    required: bool = True,
) -> object:
    _, proc = _timed_make_target(
        stack_path=stack_path,
        target=target,
        service=service,
        required=required,
    )
    return proc


def _stack_containers(client: docker.DockerClient, stack: StackInfo) -> Dict[str, Container]:
    containers: Dict[str, Container] = {}
    for service in stack.services:
        try:
            result = run_cmd(["docker", "compose", "ps", "-q", service], cwd=stack.path, check=False)
            cid = result.stdout.strip()
            if cid:
                containers[service] = client.containers.get(cid)
        except Exception:
            continue
    return containers


def collect_deployment_times(stack: StackInfo, only_container: Optional[str] = None) -> List[DeploymentMetric]:
    # Previous implementation (kept for traceability):
    # - Rebuilt each service independently: `make rebuild SERVICE=<svc>`
    # - Swallowed make failures with `check=False`
    # - Could silently return empty metrics when make failed (e.g., missing includes in mounted paths)
    #
    # Updated implementation:
    # - Default: rebuild full stack once with `make rebuild`
    # - Optional: rebuild one service with `--only-container`
    # - Fail fast with explicit command stdout/stderr when make targets fail
    # - T_startup is measured until `make is-available` succeeds
    # - T_ready is measured until `make dry-run` succeeds

    log_flow(
        f"[deployment-times] Starting stack='{stack.name}' path='{stack.path}' "
        f"only_container={only_container}"
    )
    metric_containers = stack.services or list(stack.dockerfiles.keys())
    if only_container:
        metric_containers = [name for name in metric_containers if name == only_container]

    if not metric_containers:
        log_flow(f"[deployment-times] No containers selected for stack='{stack.name}'.")
        return []

    if only_container:
        stack_build_duration, _ = _timed_make_target(
            stack_path=stack.path,
            target="rebuild",
            service=only_container,
            required=True,
        )
    else:
        stack_build_duration, _ = _timed_make_target(
            stack_path=stack.path,
            target="rebuild",
            required=True,
        )

    run_start = time.perf_counter()
    log_flow(f"[deployment-times] Starting stack run sequence for '{stack.name}'.")
    _run_make_target(stack_path=stack.path, target="run", required=True)
    _run_make_target(stack_path=stack.path, target="is-available", required=True)
    t_startup = time.perf_counter() - run_start

    _run_make_target(stack_path=stack.path, target="dry-run", required=True)
    t_ready = time.perf_counter() - run_start
    log_flow(
        f"[deployment-times] Startup completed for '{stack.name}' "
        f"(t_startup_sec={t_startup:.3f}, t_ready_sec={t_ready:.3f})."
    )

    metrics: List[DeploymentMetric] = []
    for container_name in metric_containers:
        t_build = stack_build_duration
        metrics.append(
            DeploymentMetric(
                stack=stack.name,
                stack_path=str(stack.path),
                container=container_name,
                t_build_sec=t_build,
                t_startup_sec=t_startup,
                t_total_sec=t_build + t_startup,
                t_ready_sec=t_ready,
            )
        )

    _run_make_target(stack_path=stack.path, target="stop", required=False)
    log_flow(f"[deployment-times] Finished stack='{stack.name}' with {len(metrics)} metric rows.")
    return metrics


def collect_cpu_mem_metrics(
    stack: StackInfo,
    baseline_samples: int,
    sample_interval_sec: float,
) -> List[ResourceMetric]:
    log_flow(
        f"[cpu-memory] Starting stack='{stack.name}' path='{stack.path}' "
        f"baseline_samples={baseline_samples} sample_interval_sec={sample_interval_sec}"
    )
    _run_make_target(stack_path=stack.path, target="run", required=False)
    _run_make_target(stack_path=stack.path, target="is-available", required=False)

    client = docker.from_env()
    containers = _stack_containers(client, stack)
    log_flow(f"[cpu-memory] Monitored containers: {', '.join(containers.keys()) or 'none'}")

    baseline_cpu: Dict[str, List[float]] = {k: [] for k in containers}
    baseline_mem: Dict[str, List[float]] = {k: [] for k in containers}
    baseline_disk_cumulative: Dict[str, List[float]] = {k: [] for k in containers}
    baseline_host_cpu: List[float] = []
    baseline_host_mem: List[float] = []
    baseline_host_disk_cumulative: List[float] = []
    baseline_sample_timestamps: List[float] = []

    log_flow("[cpu-memory] Collecting baseline samples...")
    baseline_phase_start = time.perf_counter()
    for _ in range(baseline_samples):
        baseline_sample_timestamps.append(time.perf_counter() - baseline_phase_start)
        host_cpu_total = 0.0
        host_mem_total = 0.0
        host_disk_total = 0.0
        for name, container in containers.items():
            stats = container.stats(stream=False)
            cpu_pct, mem_mb, blkio_total_bytes = _extract_cpu_mem_disk(stats)
            baseline_cpu[name].append(cpu_pct)
            baseline_mem[name].append(mem_mb)
            baseline_disk_cumulative[name].append(blkio_total_bytes)
            host_cpu_total += cpu_pct
            host_mem_total += mem_mb
            host_disk_total += blkio_total_bytes
        baseline_host_cpu.append(host_cpu_total)
        baseline_host_mem.append(host_mem_total)
        baseline_host_disk_cumulative.append(host_disk_total)
        time.sleep(sample_interval_sec)
    log_flow("[cpu-memory] Baseline sampling completed.")

    attack_cpu: Dict[str, List[float]] = {k: [] for k in containers}
    attack_mem: Dict[str, List[float]] = {k: [] for k in containers}
    attack_disk_cumulative: Dict[str, List[float]] = {k: [] for k in containers}
    attack_host_cpu: List[float] = []
    attack_host_mem: List[float] = []
    attack_host_disk_cumulative: List[float] = []
    attack_sample_timestamps: List[float] = []
    stop_event = threading.Event()
    attack_phase_start = time.perf_counter()

    def sampler() -> None:
        while not stop_event.is_set():
            attack_sample_timestamps.append(time.perf_counter() - attack_phase_start)
            host_cpu_total = 0.0
            host_mem_total = 0.0
            host_disk_total = 0.0
            for name, container in containers.items():
                try:
                    stats = container.stats(stream=False)
                    cpu_pct, mem_mb, blkio_total_bytes = _extract_cpu_mem_disk(stats)
                    attack_cpu[name].append(cpu_pct)
                    attack_mem[name].append(mem_mb)
                    attack_disk_cumulative[name].append(blkio_total_bytes)
                    host_cpu_total += cpu_pct
                    host_mem_total += mem_mb
                    host_disk_total += blkio_total_bytes
                except Exception:
                    continue
            attack_host_cpu.append(host_cpu_total)
            attack_host_mem.append(host_mem_total)
            attack_host_disk_cumulative.append(host_disk_total)
            time.sleep(sample_interval_sec)

    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    log_flow("[cpu-memory] Starting attack phase and concurrent sampling...")
    _run_make_target(stack_path=stack.path, target="auto-attack", required=False)
    stop_event.set()
    thread.join(timeout=5)
    if not attack_sample_timestamps:
        # Previous implementation (kept for traceability):
        # Attack samples depended entirely on background thread timing and could
        # end up empty when auto-attack completed too quickly.
        #
        # Updated implementation:
        # Guarantee at least one attack-phase sample so JSON includes a usable
        # sampled series even for short attack windows.
        host_cpu_total = 0.0
        host_mem_total = 0.0
        host_disk_total = 0.0
        for name, container in containers.items():
            try:
                stats = container.stats(stream=False)
                cpu_pct, mem_mb, blkio_total_bytes = _extract_cpu_mem_disk(stats)
                attack_cpu[name].append(cpu_pct)
                attack_mem[name].append(mem_mb)
                attack_disk_cumulative[name].append(blkio_total_bytes)
                host_cpu_total += cpu_pct
                host_mem_total += mem_mb
                host_disk_total += blkio_total_bytes
            except Exception:
                continue
        attack_host_cpu.append(host_cpu_total)
        attack_host_mem.append(host_mem_total)
        attack_host_disk_cumulative.append(host_disk_total)
        attack_sample_timestamps.append(time.perf_counter() - attack_phase_start)
    log_flow("[cpu-memory] Attack phase completed.")

    metrics: List[ResourceMetric] = []
    for name in containers:
        baseline_disk_rates = _rates_from_cumulative(baseline_disk_cumulative[name], sample_interval_sec)
        attack_disk_rates = _rates_from_cumulative(attack_disk_cumulative[name], sample_interval_sec)
        metrics.append(
            ResourceMetric(
                scope="container",
                stack=stack.name,
                stack_path=str(stack.path),
                container=name,
                sampling_interval_sec=sample_interval_sec,
                baseline_sample_timestamps_sec=baseline_sample_timestamps,
                attack_sample_timestamps_sec=attack_sample_timestamps,
                cpu_baseline_samples=baseline_cpu[name],
                cpu_attack_samples=attack_cpu[name],
                mem_baseline_samples_mb=baseline_mem[name],
                mem_attack_samples_mb=attack_mem[name],
                disk_io_baseline_samples_bps=baseline_disk_rates,
                disk_io_attack_samples_bps=attack_disk_rates,
                cpu_baseline=mean(baseline_cpu[name]),
                cpu_attack=mean(attack_cpu[name]),
                cpu_peak=max(attack_cpu[name]) if attack_cpu[name] else 0.0,
                mem_baseline_mb=mean(baseline_mem[name]),
                mem_attack_mb=mean(attack_mem[name]),
                mem_peak_mb=max(attack_mem[name]) if attack_mem[name] else 0.0,
                disk_io_baseline_bps=mean(baseline_disk_rates),
                disk_io_attack_bps=mean(attack_disk_rates),
                disk_io_peak_bps=max(attack_disk_rates) if attack_disk_rates else 0.0,
            )
        )

    baseline_host_disk_rates = _rates_from_cumulative(baseline_host_disk_cumulative, sample_interval_sec)
    attack_host_disk_rates = _rates_from_cumulative(attack_host_disk_cumulative, sample_interval_sec)
    metrics.append(
        ResourceMetric(
            # Previous implementation (kept for traceability):
            # Only per-container resource rows were returned, so host-level
            # totals requested by the experimental design were unavailable.
            #
            # Updated implementation:
            # Add a dedicated host aggregate row with `container="__host__"`.
            # This preserves backward compatibility for container rows and
            # introduces system-level CPU, memory, and disk I/O metrics.
            scope="host",
            stack=stack.name,
            stack_path=str(stack.path),
            container="__host__",
            sampling_interval_sec=sample_interval_sec,
            baseline_sample_timestamps_sec=baseline_sample_timestamps,
            attack_sample_timestamps_sec=attack_sample_timestamps,
            cpu_baseline_samples=baseline_host_cpu,
            cpu_attack_samples=attack_host_cpu,
            mem_baseline_samples_mb=baseline_host_mem,
            mem_attack_samples_mb=attack_host_mem,
            disk_io_baseline_samples_bps=baseline_host_disk_rates,
            disk_io_attack_samples_bps=attack_host_disk_rates,
            cpu_baseline=mean(baseline_host_cpu),
            cpu_attack=mean(attack_host_cpu),
            cpu_peak=max(attack_host_cpu) if attack_host_cpu else 0.0,
            mem_baseline_mb=mean(baseline_host_mem),
            mem_attack_mb=mean(attack_host_mem),
            mem_peak_mb=max(attack_host_mem) if attack_host_mem else 0.0,
            disk_io_baseline_bps=mean(baseline_host_disk_rates),
            disk_io_attack_bps=mean(attack_host_disk_rates),
            disk_io_peak_bps=max(attack_host_disk_rates) if attack_host_disk_rates else 0.0,
        )
    )

    _run_make_target(stack_path=stack.path, target="stop", required=False)
    log_flow(f"[cpu-memory] Finished stack='{stack.name}' with {len(metrics)} metric rows.")
    return metrics


def _normalize_probe_protocol(raw_value: object) -> str:
    protocol = str(raw_value or "tcp").strip().lower()
    if protocol not in {"tcp", "udp"}:
        return "tcp"
    return protocol


def _normalize_probe_port(raw_value: object) -> Optional[int]:
    try:
        port_value = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return None
    if port_value < 1 or port_value > 65535:
        return None
    return port_value


def _load_network_plan(network_plan_path: Optional[Path]) -> List[Tuple[str, List[Tuple[str, int, str]]]]:
    # Previous implementation (kept for traceability):
    # if not network_plan_path:
    #     return []
    # payload = json.loads(network_plan_path.read_text(encoding="utf-8"))
    # result: List[Tuple[str, List[str]]] = []
    # for item in payload:
    #     source = item.get("container")
    #     targets = item.get("probed_services", [])
    #     if source and isinstance(targets, list):
    #         result.append((source, targets))
    # return result
    #
    # Updated implementation:
    # - Validates entry types
    # - Expects per-service probes with container + port + optional protocol type
    # - Normalizes protocol to tcp/udp (default tcp)
    # - De-duplicates probes while preserving order
    if not network_plan_path:
        return []
    payload = json.loads(network_plan_path.read_text(encoding="utf-8"))
    result: List[Tuple[str, List[Tuple[str, int, str]]]] = []
    if not isinstance(payload, list):
        return result

    for item in payload:
        if not isinstance(item, dict):
            continue
        source = item.get("container")
        targets = item.get("probed_services", [])
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(targets, list):
            continue

        normalized_probes: List[Tuple[str, int, str]] = []
        for target in targets:
            if not isinstance(target, dict):
                continue

            target_name = str(target.get("container", "") or target.get("name", "")).strip()
            target_port = _normalize_probe_port(target.get("port"))
            target_protocol = _normalize_probe_protocol(target.get("type", "tcp"))

            if not target_name or target_port is None:
                continue

            probe = (target_name, target_port, target_protocol)
            if probe not in normalized_probes:
                normalized_probes.append(probe)

        if normalized_probes:
            result.append((source.strip(), normalized_probes))
    return result


def _compose_exec_sh(stack: StackInfo, source: str, shell_command: str) -> object:
    return run_cmd(
        ["docker", "compose", "exec", "-T", source, "sh", "-lc", shell_command],
        cwd=stack.path,
        check=False,
    )


def _resolve_service_container_id(stack: StackInfo, service_name: str) -> Optional[str]:
    result = run_cmd(["docker", "compose", "ps", "-q", service_name], cwd=stack.path, check=False)
    cid = result.stdout.strip()
    if not cid:
        return None
    return cid


def _resolve_service_network_ips(stack: StackInfo, service_name: str) -> Dict[str, str]:
    cid = _resolve_service_container_id(stack=stack, service_name=service_name)
    if not cid:
        return {}

    inspect_result = run_cmd(["docker", "inspect", cid], cwd=stack.path, check=False)
    if inspect_result.returncode != 0:
        return {}

    try:
        payload = json.loads(inspect_result.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list) or not payload:
        return {}

    network_settings = payload[0].get("NetworkSettings", {})
    networks = network_settings.get("Networks", {})
    if not isinstance(networks, dict):
        return {}

    ip_by_network: Dict[str, str] = {}
    for network_name, network_details in networks.items():
        if not isinstance(network_details, dict):
            continue
        ip_address = str(network_details.get("IPAddress", "")).strip()
        if ip_address:
            ip_by_network[network_name] = ip_address
    return ip_by_network


def _resolve_target_ip_for_source(
    stack: StackInfo,
    source: str,
    target: str,
    ip_cache: Dict[str, Dict[str, str]],
) -> str:
    target_candidate = target.strip()
    if IPV4_RE.match(target_candidate):
        return target_candidate

    source_network_ips = ip_cache.setdefault(source, _resolve_service_network_ips(stack=stack, service_name=source))
    target_network_ips = ip_cache.setdefault(target_candidate, _resolve_service_network_ips(stack=stack, service_name=target_candidate))

    for network_name, source_ip in source_network_ips.items():
        if source_ip and network_name in target_network_ips:
            resolved_target_ip = target_network_ips[network_name].strip()
            if resolved_target_ip:
                return resolved_target_ip

    if target_network_ips:
        # Stable fallback when no shared network is detected between source and target.
        network_name = sorted(target_network_ips.keys())[0]
        return target_network_ips[network_name].strip()

    # If target is not a compose service name, keep it as provided so host DNS can resolve it.
    return target_candidate


def _parse_ping_sample(output: str, returncode: int) -> Tuple[float, float]:
    time_match = PING_TIME_RE.search(output)
    loss_match = PING_LOSS_RE.search(output)
    rtt = float(time_match.group(1)) if time_match else 0.0
    loss = float(loss_match.group(1)) if loss_match else (100.0 if returncode != 0 else 0.0)
    return rtt, loss


def _parse_nmap_sample(output: str, returncode: int, expected_port: int, expected_protocol: str) -> Tuple[float, float]:
    latency_match = NMAP_HOST_LATENCY_RE.search(output)
    latency_ms = (float(latency_match.group(1)) * 1000.0) if latency_match else 0.0

    open_port_re = re.compile(
        rf"^\s*{expected_port}/{re.escape(expected_protocol)}\s+open\b",
        re.IGNORECASE | re.MULTILINE,
    )
    has_expected_open_port = bool(open_port_re.search(output))

    if returncode != 0:
        return 0.0, 100.0
    if not latency_match:
        return 0.0, 100.0
    if not has_expected_open_port:
        # The scan reached the host but found no open port for this protocol.
        # We mark this probe as full loss to keep service-level probing explicit.
        return 0.0, 100.0
    return latency_ms, 0.0


def _ensure_host_nmap_available(stack: StackInfo) -> None:
    # Previous implementation (kept for traceability):
    # Checked nmap availability inside each source container.
    #
    # Updated implementation:
    # Check nmap + sudo availability in the collector runtime because TCP/UDP
    # probes are now executed from the host-side collector process.
    log_flow("[network] Validating nmap availability in collector runtime...")
    nmap_check = run_cmd(["sh", "-lc", "command -v nmap >/dev/null 2>&1"], cwd=stack.path, check=False)
    if nmap_check.returncode != 0:
        raise RuntimeError(
            "nmap is required in the metrics collector runtime environment. "
            "Install nmap on the host (or collector container) before running network metrics."
        )

    sudo_check = run_cmd(["sh", "-lc", "command -v sudo >/dev/null 2>&1"], cwd=stack.path, check=False)
    if sudo_check.returncode != 0:
        raise RuntimeError(
            "sudo is required for UDP nmap scans (nmap -sU). "
            "Install sudo in the metrics collector runtime environment."
        )


def _run_tcp_probe(stack: StackInfo, target_ip: str, port: int) -> Tuple[float, float]:
    # Previous implementation (kept for traceability):
    # Ran TCP nmap inside source container with -sS then fallback to -sT.
    #
    # Updated implementation:
    # Run TCP nmap from host-side collector runtime using -sT (full TCP connect
    # three-way handshake semantics).
    tcp_result = run_cmd(
        ["nmap", "-Pn", "-n", "--open", "-sT", "-p", str(port), target_ip],
        cwd=stack.path,
        check=False,
    )
    tcp_output = f"{tcp_result.stdout}\n{tcp_result.stderr}"
    return _parse_nmap_sample(tcp_output, tcp_result.returncode, expected_port=port, expected_protocol="tcp")


def _run_udp_probe(stack: StackInfo, target_ip: str, port: int) -> Tuple[float, float]:
    # Previous implementation (kept for traceability):
    # Ran UDP nmap inside source container without sudo.
    #
    # Updated implementation:
    # Run UDP nmap from host-side collector runtime using sudo.
    udp_result = run_cmd(
        ["sudo", "nmap", "-Pn", "-n", "--open", "-sU", "-p", str(port), target_ip],
        cwd=stack.path,
        check=False,
    )
    udp_output = f"{udp_result.stdout}\n{udp_result.stderr}"
    return _parse_nmap_sample(udp_output, udp_result.returncode, expected_port=port, expected_protocol="udp")


def collect_network_metrics(
    stack: StackInfo,
    sample_interval_sec: float,
    network_plan_path: Optional[Path] = None,
) -> List[NetworkMetric]:
    # Previous implementation (kept for traceability):
    # - Sampled only ICMP (`ping`) per source/target pair
    # - Returned one row per pair with protocol defaulting to "icmp"
    #
    # Updated implementation:
    # - Keeps ICMP probing from the source container
    # - Resolves target service names from network plan into container IP addresses
    # - Runs host-side nmap probes for configured target port/protocol pairs
    # - Emits ICMP rows per source-target plus service rows per configured probe
    log_flow(
        f"[network] Starting stack='{stack.name}' path='{stack.path}' "
        f"sample_interval_sec={sample_interval_sec} network_plan={network_plan_path}"
    )
    _run_make_target(stack_path=stack.path, target="run", required=False)
    _run_make_target(stack_path=stack.path, target="is-available", required=False)

    try:
        service_probe_plan: List[Tuple[str, str, int, str]] = []
        ping_pair_plan: List[Tuple[str, str]] = []
        explicit_plan = _load_network_plan(network_plan_path)
        log_flow(f"[network] Loaded explicit probe plan entries: {len(explicit_plan)}")
        if explicit_plan:
            # Previous implementation (kept for traceability):
            # for src, targets in explicit_plan:
            #     for target, port, protocol in targets:
            #         probe_plan.append((src, target, port, protocol))
            #
            # Updated implementation:
            # Explicit network plan enables both ICMP and service probes.
            # ICMP source-target pairs are derived from service probe definitions.
            for src, targets in explicit_plan:
                for target, port, protocol in targets:
                    ping_pair = (src, target)
                    if ping_pair not in ping_pair_plan:
                        ping_pair_plan.append(ping_pair)
                    service_probe_plan.append((src, target, port, protocol))
        else:
            # Previous implementation (kept for traceability):
            # When no explicit plan was provided, probing used service names and
            # generated default TCP probes on port 80.
            #
            # Updated implementation:
            # Without network plan, run ICMP-only probing between the first
            # service and the remaining services. No TCP/UDP service probes are
            # executed in this mode.
            services = stack.services
            if services:
                anchor = services[0]
                for target in services[1:]:
                    ping_pair_plan.append((anchor, target))
        log_flow(
            "[network] Planned probes: "
            f"icmp_pairs={len(ping_pair_plan)} service_probes={len(service_probe_plan)}"
        )

        if service_probe_plan:
            _ensure_host_nmap_available(stack=stack)
        else:
            log_flow("[network] No service probes configured; skipping nmap availability checks.")

        ip_cache: Dict[str, Dict[str, str]] = {}
        resolved_ping_pairs: List[Tuple[str, str, str]] = []
        for source, target in ping_pair_plan:
            resolved_target_ip = _resolve_target_ip_for_source(
                stack=stack,
                source=source,
                target=target,
                ip_cache=ip_cache,
            )
            resolved_ping_pairs.append((source, target, resolved_target_ip))
        if resolved_ping_pairs:
            log_flow(
                "[network] Resolved ICMP pairs: "
                + ", ".join(
                    f"{source}->{target}({target_ip})"
                    for source, target, target_ip in resolved_ping_pairs
                )
            )

        resolved_service_probes: List[Tuple[str, str, str, int, str]] = []
        for source, target, port, protocol in service_probe_plan:
            resolved_target_ip = _resolve_target_ip_for_source(
                stack=stack,
                source=source,
                target=target,
                ip_cache=ip_cache,
            )
            resolved_service_probes.append((source, target, resolved_target_ip, port, protocol))
        if resolved_service_probes:
            log_flow(
                "[network] Resolved service probes: "
                + ", ".join(
                    f"{source}->{target}({target_ip})/{port}/{protocol}"
                    for source, target, target_ip, port, protocol in resolved_service_probes
                )
            )

        icmp_samples: Dict[Tuple[str, str], List[Tuple[float, float]]] = {
            (source, target): []
            for (source, target, _) in resolved_ping_pairs
        }
        service_samples: Dict[Tuple[str, str, int, str], List[Tuple[float, float]]] = {
            (source, target, port, protocol): []
            for (source, target, _, port, protocol) in resolved_service_probes
        }
        stop_event = threading.Event()
        sample_timestamps: List[float] = []
        monitor_phase_start = time.perf_counter()

        def monitor() -> None:
            while not stop_event.is_set():
                sample_timestamps.append(time.perf_counter() - monitor_phase_start)
                for source, target, target_ip in resolved_ping_pairs:
                    ping_result = _compose_exec_sh(
                        stack=stack,
                        source=source,
                        shell_command=f"ping -c 1 -W 1 {shlex.quote(target_ip)}",
                    )
                    ping_output = f"{ping_result.stdout}\n{ping_result.stderr}"
                    icmp_samples[(source, target)].append(
                        _parse_ping_sample(ping_output, ping_result.returncode)
                    )

                for source, target, target_ip, port, protocol in resolved_service_probes:
                    if protocol == "udp":
                        probe_sample = _run_udp_probe(stack=stack, target_ip=target_ip, port=port)
                    else:
                        probe_sample = _run_tcp_probe(stack=stack, target_ip=target_ip, port=port)
                    service_samples[(source, target, port, protocol)].append(probe_sample)
                time.sleep(sample_interval_sec)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        log_flow("[network] Monitor thread started. Launching auto-attack phase...")
        _run_make_target(stack_path=stack.path, target="auto-attack", required=False)
        stop_event.set()
        thread.join(timeout=5)
        log_flow("[network] Monitor thread stopped. Aggregating samples...")

        metrics: List[NetworkMetric] = []
        for pair, values in icmp_samples.items():
            rtts = [item[0] for item in values if item[0] > 0]
            losses = [item[1] for item in values]
            metrics.append(
                NetworkMetric(
                    stack=stack.name,
                    stack_path=str(stack.path),
                    source=pair[0],
                    target=pair[1],
                    port=None,
                    protocol="icmp",
                    probe_origin="source_container",
                    sampling_interval_sec=sample_interval_sec,
                    sample_timestamps_sec=sample_timestamps,
                    rtt_samples_ms=[item[0] for item in values],
                    packet_loss_samples_pct=losses,
                    rtt_avg_ms=mean(rtts),
                    rtt_peak_ms=max(rtts) if rtts else 0.0,
                    packet_loss_rate=mean(losses),
                )
            )

        for pair, values in service_samples.items():
            rtts = [item[0] for item in values if item[0] > 0]
            losses = [item[1] for item in values]
            metrics.append(
                NetworkMetric(
                    stack=stack.name,
                    stack_path=str(stack.path),
                    source=pair[0],
                    target=pair[1],
                    port=pair[2],
                    protocol=pair[3],
                    probe_origin="host_runtime",
                    sampling_interval_sec=sample_interval_sec,
                    sample_timestamps_sec=sample_timestamps,
                    rtt_samples_ms=[item[0] for item in values],
                    packet_loss_samples_pct=losses,
                    rtt_avg_ms=mean(rtts),
                    rtt_peak_ms=max(rtts) if rtts else 0.0,
                    packet_loss_rate=mean(losses),
                )
            )
        log_flow(f"[network] Finished stack='{stack.name}' with {len(metrics)} metric rows.")
        return metrics
    finally:
        _run_make_target(stack_path=stack.path, target="stop", required=False)
        log_flow(f"[network] Stack teardown requested for '{stack.name}'.")
