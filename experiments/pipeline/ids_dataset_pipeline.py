#!/usr/bin/env python3
"""
Build an IDS-ready flow dataset from:

Traffic -> PCAP capture -> Suricata alerts -> NFStream flows -> Flow labeling -> CSV/Parquet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional

import typer

from experiments.core.timing import fix_timestamp_to_rome_iso

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments import config as cfg
from experiments.core.scenario import EXPECTED_SIDS

ATTACK_TYPE_BY_SID: Dict[int, str] = {
    2000001: "sip_spoofing",
    2000002: "sip_register_flood",
    2000003: "sip_overflow",
    2000004: "rtp_injection",
    2000005: "coturn_access_bypass",
    2000006: "remote_code_execution",
    2000007: "nosql_injection",
    2000008: "xss",
    2000009: "permission_abuse",
    2000010: "xss",
    # Backward compatibility with previous local.rules SIDs
    1000001: "sip_spoofing",
    1000002: "sip_register_flood",
    1000003: "sip_overflow",
    1000004: "rtp_injection",
    1000005: "coturn_access_bypass",
    1000006: "remote_code_execution",
    1000008: "xss",
    1000009: "permission_abuse",
}

# No longer needed: lab_ready IPC events provide explicit expected_sids and attack_type.
# Removed: EXPECTED_ALERT_SIDS_BY_SCENARIO, ATTACK_TYPE_BY_SCENARIO

# Application names that are always background traffic; never expected attack for RTC scenarios.
_BACKGROUND_APP_NAMES: frozenset = frozenset({
    "MDNS", "DNS", "IGMP", "IGMPV6", "ICMP", "ICMPV6", "ARP", "SSDP", "LLMNR", "DHCP", "NTP",
})


@dataclass
class AlertRecord:
    timestamp: datetime
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str
    sid: Optional[int]
    msg: str
    attack_type: str


@dataclass
class AttackEvent:
    start_utc: datetime
    end_utc: datetime
    scenario_id: Optional[int]
    instance: Optional[str]
    expected_sids: Optional[List[int]] = None

    # Set by Makefile via IPC (lab_ready event) when the scenario has fixed IP topology.
    attacker_ips: List[str] = field(default_factory=list)
    victim_ips: List[str] = field(default_factory=list)
    attack_type: Optional[str] = None
    probe_targets: List[str] = field(default_factory=list)
    probe_protocols: List[str] = field(default_factory=list)

@dataclass
class EventValidationResult:
    event_index: int
    scenario_id: Optional[int]
    instance: Optional[str]
    expected_sids: List[int]
    matched_sids: List[int]
    unexpected_sids: List[int]
    detected: bool


@dataclass
class RunnerAttackWindow:
    start_utc: datetime
    end_utc: datetime
    scenario_id: Optional[int]
    instance: Optional[str]
    source: str
    attacker_ip: Optional[str] = None
    victim_ip: Optional[str] = None
    attack_type: Optional[str] = None
    probe_targets: List[str] = field(default_factory=list)
    probe_protocols: List[str] = field(default_factory=list)


@dataclass
class LabMetadata:
    """Metadata extracted from lab_ready IPC event for explicit ground truth."""
    scenario_id: Optional[int]
    instance: Optional[str]
    expected_sids: List[int] = field(default_factory=list)
    attack_type: Optional[str] = None
    attacker_ip: Optional[str] = None
    victim_ip: Optional[str] = None
    probe_targets: List[str] = field(default_factory=list)
    probe_protocols: List[str] = field(default_factory=list)


def _parse_comma_separated_ints(raw: Any) -> List[int]:
    """Parse comma-separated string of integers, returning list of ints."""
    if not raw:
        return []
    values: List[int] = []
    for token in str(raw).split(","):
        clean = token.strip()
        if clean.isdigit():
            values.append(int(clean))
    return values


def _parse_comma_separated_strings(raw: Any) -> List[str]:
    """Parse comma-separated string, returning list of non-empty strings."""
    if not raw:
        return []
    return [token.strip() for token in str(raw).split(",") if token.strip()]


def _extract_lab_metadata_from_ipc_events(
    ipc_events: List[Dict[str, Any]]
) -> Dict[tuple[Optional[int], Optional[str]], LabMetadata]:
    """Extract lab metadata from lab_ready IPC events.

    Returns a dict mapping (scenario_id, instance) to LabMetadata.
    Makefile sends lab_ready with fields: expected_sids, attack_type, attacker_ip,
    victim_ip, probe_targets, probe_protocols.
    """
    metadata_map: Dict[tuple[Optional[int], Optional[str]], LabMetadata] = {}

    for event in ipc_events:
        if not isinstance(event, dict):
            continue
        state = str(event.get("state", "")).strip()
        if state != "lab_ready":
            continue

        scenario_id = _int_or_none(event.get("scenario"))
        instance = str(event.get("instance")) if event.get("instance") is not None else None
        key = (scenario_id, instance)

        expected_sids = _parse_comma_separated_ints(event.get("expected_sids"))
        attack_type = str(event.get("attack_type")).strip() if event.get("attack_type") else None
        attacker_ip = str(event.get("attacker_ip")).strip() if event.get("attacker_ip") else None
        victim_ip = str(event.get("victim_ip")).strip() if event.get("victim_ip") else None
        probe_targets = _parse_comma_separated_strings(event.get("probe_targets"))
        probe_protocols = _parse_comma_separated_strings(event.get("probe_protocols"))

        metadata_map[key] = LabMetadata(
            scenario_id=scenario_id,
            instance=instance,
            expected_sids=expected_sids,
            attack_type=attack_type,
            attacker_ip=attacker_ip,
            victim_ip=victim_ip,
            probe_targets=probe_targets,
            probe_protocols=probe_protocols,
        )

    return metadata_map


def _parse_datetime_utc(raw_value: Any) -> Optional[datetime]:
    if raw_value is None:
        return None

    raw = str(raw_value).strip()
    if not raw:
        return None

    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)

    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    # Snort full alert style (MM/DD-HH:MM:SS.uuuuuu)
    for year in (datetime.now(timezone.utc).year, datetime.now(timezone.utc).year - 1):
        try:
            parsed = datetime.strptime(f"{year}/{raw}", "%Y/%m/%d-%H:%M:%S.%f")
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_datetime_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_attack_windows_from_ipc_events(
    ipc_events: List[Dict[str, Any]],
    allowed_runs: set[tuple[Optional[int], Optional[str]]] | None,
) -> List[RunnerAttackWindow]:
    pending: List[Dict[str, Any]] = []
    windows: List[RunnerAttackWindow] = []

    for event in ipc_events:
        state = str(event.get("state", "")).strip()
        if state not in {"attack_start", "attack_end"}:
            continue

        scenario_id = _int_or_none(event.get("scenario"))
        instance = str(event.get("instance")) if event.get("instance") is not None else None
        if allowed_runs is not None and (scenario_id, instance) not in allowed_runs:
            continue

        timestamp = _parse_datetime_utc(event.get("ts_utc"))
        if timestamp is None:
            continue

        attack = event.get("attack")
        attacker_ip = str(event["attacker_ip"]) if event.get("attacker_ip") else None
        victim_ip = str(event["victim_ip"]) if event.get("victim_ip") else None
        if state == "attack_start":
            pending.append(
                {
                    "start_utc": timestamp,
                    "scenario_id": scenario_id,
                    "instance": instance,
                    "attack": attack,
                    "attacker_ip": attacker_ip,
                    "victim_ip": victim_ip,
                }
            )
            continue

        match_index = -1
        for index in range(len(pending) - 1, -1, -1):
            item = pending[index]
            if (
                item.get("scenario_id") == scenario_id
                and item.get("instance") == instance
                and item.get("attack") == attack
            ):
                match_index = index
                break

        if match_index == -1:
            continue

        item = pending.pop(match_index)
        start = item["start_utc"]
        if timestamp < start:
            continue
        windows.append(
            RunnerAttackWindow(
                start_utc=start,
                end_utc=timestamp,
                scenario_id=scenario_id,
                instance=instance,
                source="scenario_runner_ipc",
                attacker_ip=item.get("attacker_ip"),
                victim_ip=item.get("victim_ip"),
            )
        )

    return windows


# Removed: _result_to_attack_windows - replaced by explicit IPC attack_start/attack_end events.


def _int_or_zero(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_proto(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"

    proto_by_number = {
        "1": "icmp",
        "6": "tcp",
        "17": "udp",
    }
    return proto_by_number.get(raw, raw)


def _attack_type_from_fields(sid: Optional[int], msg: str) -> str:
    if sid is not None and sid in ATTACK_TYPE_BY_SID:
        return ATTACK_TYPE_BY_SID[sid]

    msg_lower = msg.lower()
    if "spoof" in msg_lower:
        return "sip_spoofing"
    if "flood" in msg_lower:
        return "sip_register_flood"
    if "overflow" in msg_lower:
        return "sip_overflow"
    if "rtp" in msg_lower:
        return "rtp_injection"
    if "turn" in msg_lower or "coturn" in msg_lower:
        return "coturn_access_bypass"
    if "rce" in msg_lower or "webshell" in msg_lower:
        return "remote_code_execution"
    if "nosql" in msg_lower:
        return "nosql_injection"
    if "xss" in msg_lower:
        return "xss"
    if "permission" in msg_lower or "capture endpoint" in msg_lower:
        return "permission_abuse"
    return "unknown_attack"


def load_alerts(alert_file: Path) -> List[AlertRecord]:
    alerts: List[AlertRecord] = []
    if not alert_file.exists():
        raise FileNotFoundError(f"Alert file not found: {alert_file}")

    for raw_line in alert_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith("{"):
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        timestamp = _parse_datetime_utc(payload.get("timestamp") or payload.get("time"))
        if timestamp is None:
            continue

        # Support both Snort and Suricata formats
        # Snort: {"sid": 123, "msg": "...", "src_ip": "...", "dst_ip": "..."}
        # Suricata: {"alert": {"signature_id": 123, "signature": "..."}, "src_ip": "...", "dest_ip": "..."}
        alert_obj = payload.get("alert", {})
        sid_raw = alert_obj.get("signature_id") or payload.get("sid")
        sid = _int_or_zero(sid_raw) if sid_raw is not None else None
        if sid == 0:
            sid = None

        msg = str(
            alert_obj.get("signature")
            or payload.get("msg")
            or payload.get("message")
            or ""
        ).strip()
        attack_type = _attack_type_from_fields(sid=sid, msg=msg)

        alerts.append(
            AlertRecord(
                timestamp=timestamp,
                src_ip=str(
                    payload.get("src_ip")
                    or payload.get("src_ap")
                    or payload.get("src_addr")
                    or ""
                ),
                dst_ip=str(
                    payload.get("dest_ip")
                    or payload.get("dst_ip")
                    or payload.get("dst_ap")
                    or payload.get("dst_addr")
                    or ""
                ),
                src_port=_int_or_zero(payload.get("src_port")),
                dst_port=_int_or_zero(payload.get("dest_port") or payload.get("dst_port")),
                protocol=_normalize_proto(payload.get("proto")),
                sid=sid,
                msg=msg,
                attack_type=attack_type,
            )
        )

    return alerts


def load_attack_events(events_file: Path) -> List[AttackEvent]:
    if not events_file.exists():
        raise FileNotFoundError(f"Attack events file not found: {events_file}")

    payload = json.loads(events_file.read_text(encoding="utf-8"))

    if isinstance(payload, dict) and "events" in payload:
        events_raw = payload["events"]
    elif isinstance(payload, list):
        events_raw = payload
    else:
        raise ValueError("Unsupported attack events JSON format")

    events: List[AttackEvent] = []
    for item in events_raw:
        start = _parse_datetime_utc(item.get("start_utc"))
        end = _parse_datetime_utc(item.get("end_utc"))
        if start is None or end is None:
            continue

        events.append(
            AttackEvent(
                start_utc=start,
                end_utc=end,
                scenario_id=_int_or_none(item.get("scenario_id")),
                instance=item.get("instance"),
                expected_sids=item.get("expected_sids"),
                attacker_ips=list(item.get("attacker_ips") or []),
                victim_ips=list(item.get("victim_ips") or []),
                attack_type=str(item.get("attack_type")).strip() if item.get("attack_type") else None,
                probe_targets=list(item.get("probe_targets") or []),
                probe_protocols=list(item.get("probe_protocols") or []),
            )
        )

    return events


def build_attack_events_from_runner_summary(summary_file: Path, output_file: Path) -> None:
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Runner summary does not contain a 'results' list")

    # Change rationale: build event windows from explicit attack markers when available.
    events: List[Dict[str, Any]] = []
    successful_runs = {
        (_int_or_none(result.get("scenario_id")), str(result.get("instance")))
        for result in results
        if bool(result.get("success"))
    }
    ipc_events = payload.get("ipc_events", [])
    
    # Extract explicit ground truth metadata from lab_ready events.
    lab_metadata = (
        _extract_lab_metadata_from_ipc_events(ipc_events)
        if isinstance(ipc_events, list)
        else {}
    )
    
    windows = (
        _load_attack_windows_from_ipc_events(ipc_events, successful_runs)
        if isinstance(ipc_events, list)
        else []
    )

    if not windows:
        raise ValueError(
            "No attack windows found in IPC events. "
            "Ensure Makefile sends attack_start/attack_end IPC events."
        )

    for window in windows:
        key = (window.scenario_id, window.instance)
        metadata = lab_metadata.get(key)

        # Require explicit metadata from lab_ready IPC event.
        if not metadata or not metadata.expected_sids:
            raise ValueError(
                f"Missing lab_ready metadata for scenario={window.scenario_id} instance={window.instance}. "
                "Ensure Makefile sends lab_ready with expected_sids, attack_type, attacker_ip, victim_ip."
            )

        events.append(
            {
                "scenario_id": window.scenario_id,
                "instance": window.instance,
                "start_utc": _format_datetime_utc(window.start_utc),
                "end_utc": _format_datetime_utc(window.end_utc),
                "expected_sids": metadata.expected_sids,
                "attack_type": metadata.attack_type,
                "source": window.source,
                "attacker_ips": [window.attacker_ip] if window.attacker_ip else [],
                "victim_ips": [window.victim_ip] if window.victim_ip else [],
                "probe_targets": metadata.probe_targets,
                "probe_protocols": metadata.probe_protocols,
            }
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps({"events": events}, indent=2), encoding="utf-8")


def load_attack_events_from_runner_summary(summary_file: Path, only_success: bool) -> List[AttackEvent]:
    payload = json.loads(summary_file.read_text(encoding="utf-8"))
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("Runner summary does not contain a 'results' list")

    # Change rationale: use structured IPC attack windows before falling back to logs.
    events: List[AttackEvent] = []
    allowed_runs = None
    if only_success:
        allowed_runs = {
            (_int_or_none(item.get("scenario_id")), str(item.get("instance")))
            for item in results
            if bool(item.get("success"))
        }

    ipc_events = payload.get("ipc_events", [])
    
    # Extract explicit ground truth metadata from lab_ready events.
    lab_metadata = (
        _extract_lab_metadata_from_ipc_events(ipc_events)
        if isinstance(ipc_events, list)
        else {}
    )
    
    windows = (
        _load_attack_windows_from_ipc_events(ipc_events, allowed_runs)
        if isinstance(ipc_events, list)
        else []
    )

    if not windows:
        raise ValueError(
            "No attack windows found in IPC events. "
            "Ensure Makefile sends attack_start/attack_end IPC events."
        )

    result_events: List[AttackEvent] = []
    for window in windows:
        key = (window.scenario_id, window.instance)
        metadata = lab_metadata.get(key)

        # Require explicit metadata from lab_ready IPC event.
        if not metadata or not metadata.expected_sids:
            raise ValueError(
                f"Missing lab_ready metadata for scenario={window.scenario_id} instance={window.instance}. "
                "Ensure Makefile sends lab_ready with expected_sids, attack_type, attacker_ip, victim_ip."
            )

        result_events.append(
            AttackEvent(
                start_utc=window.start_utc,
                end_utc=window.end_utc,
                scenario_id=window.scenario_id,
                instance=window.instance,
                expected_sids=metadata.expected_sids,
                attacker_ips=[window.attacker_ip] if window.attacker_ip else [],
                victim_ips=[window.victim_ip] if window.victim_ip else [],
                attack_type=metadata.attack_type,
                probe_targets=metadata.probe_targets,
                probe_protocols=metadata.probe_protocols,
            )
        )
    return result_events


def _collect_pcap_files(pcap_input: Path) -> List[Path]:
    if pcap_input.is_file():
        return [pcap_input]

    if not pcap_input.is_dir():
        raise FileNotFoundError(f"PCAP input not found: {pcap_input}")

    files = sorted(pcap_input.glob("*.pcap"))
    if not files:
        raise ValueError(f"No .pcap files found in: {pcap_input}")
    return files


def _protocol_from_flow(flow: Dict[str, Any]) -> str:
    value = flow.get("protocol")
    return _normalize_proto(value)


def _flow_time_bounds(flow: Dict[str, Any]) -> tuple[datetime, datetime]:
    start_ms = int(flow.get("bidirectional_first_seen_ms") or 0)
    end_ms = int(flow.get("bidirectional_last_seen_ms") or start_ms)

    start = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
    end = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc)
    return start, end


def _flow_matches_alert(
    flow: Dict[str, Any],
    alert: AlertRecord,
    time_window_sec: float,
) -> bool:
    flow_src_ip = str(flow.get("src_ip") or "")
    flow_dst_ip = str(flow.get("dst_ip") or "")
    flow_src_port = _int_or_zero(flow.get("src_port"))
    flow_dst_port = _int_or_zero(flow.get("dst_port"))
    flow_protocol = _protocol_from_flow(flow)

    flow_start, flow_end = _flow_time_bounds(flow)
    window = timedelta(seconds=time_window_sec)

    time_ok = (flow_start - window) <= alert.timestamp <= (flow_end + window)
    if not time_ok:
        return False

    proto_ok = (alert.protocol == "unknown") or (flow_protocol == "unknown") or (alert.protocol == flow_protocol)
    if not proto_ok:
        return False

    direct_match = (
        alert.src_ip == flow_src_ip
        and alert.dst_ip == flow_dst_ip
        and (alert.src_port == 0 or flow_src_port == 0 or alert.src_port == flow_src_port)
        and (alert.dst_port == 0 or flow_dst_port == 0 or alert.dst_port == flow_dst_port)
    )
    reverse_match = (
        alert.src_ip == flow_dst_ip
        and alert.dst_ip == flow_src_ip
        and (alert.src_port == 0 or flow_dst_port == 0 or alert.src_port == flow_dst_port)
        and (alert.dst_port == 0 or flow_src_port == 0 or alert.dst_port == flow_src_port)
    )

    return direct_match or reverse_match


def _find_overlapping_attack_event(
    flow: Dict[str, Any], events: List[AttackEvent]
) -> Optional[AttackEvent]:
    """Return the first AttackEvent whose window overlaps this flow, or None.

    Also returns None for flows whose application is pure background traffic
    (MDNS, DNS, IGMP, …) that can never be RTC attack traffic.
    """
    app_name = str(flow.get("application_name", "")).upper()
    flow_start, flow_end = _flow_time_bounds(flow)
    for event in events:
        if not (flow_start <= event.end_utc and flow_end >= event.start_utc):
            continue
        # If the event carries explicit IP endpoints, require the flow to involve them.
        if event.attacker_ips or event.victim_ips:
            if _flow_involves_attack_endpoints(flow, event):
                return event
        else:
            # Fallback for HTTP labs where no fixed IPs are provided: exclude
            # known background protocols that cannot be RTC attack traffic.
            app_name = str(flow.get("application_name", "")).upper()
            if app_name not in _BACKGROUND_APP_NAMES:
                return event
    return None


def _flow_involves_attack_endpoints(flow: Dict[str, Any], event: AttackEvent) -> bool:
    """Return True if the flow involves BOTH attacker and victim endpoints.

    A flow is attack traffic only if it's between the attacker and victim,
    not just any traffic to/from the victim during the attack window.
    This prevents labeling legitimate client traffic to the victim as malicious.
    """
    src_ip = str(flow.get("src_ip", ""))
    dst_ip = str(flow.get("dst_ip", ""))

    attacker_ips = set(event.attacker_ips)
    victim_ips = set(event.victim_ips)

    involves_attacker = src_ip in attacker_ips or dst_ip in attacker_ips
    involves_victim = src_ip in victim_ips or dst_ip in victim_ips

    return involves_attacker and involves_victim


def extract_flows(pcap_files: Iterable[Path]) -> List[Dict[str, Any]]:
    try:
        from nfstream import NFStreamer
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise SystemExit(
            "Missing dependency 'nfstream'. Install with: pip install nfstream"
        ) from exc

    flows: List[Dict[str, Any]] = []
    for pcap_file in pcap_files:
        streamer = NFStreamer(source=str(pcap_file), statistical_analysis=True)
        for flow in streamer:
            # nfstream >= 6.4 removed to_dict(); use keys()/values() instead
            item = dict(zip(flow.keys(), flow.values()))
            item["pcap_file"] = str(pcap_file)
            flows.append(item)
    return flows


def _run_suricata_container(
    pcap_file: Path,
    output_dir: Path,
    project_root: Path,
    suricata_image: str,
    suricata_rules: str,
    eve_filename: str,
) -> None:
    try:
        import docker
        from docker.errors import ContainerError, DockerException
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise SystemExit("Missing dependency 'docker'. Install experiments requirements.") from exc

    client = docker.from_env()
    command = [
        "suricata",
        "-r",
        f"/pcaps/{pcap_file.name}",
        "-S",
        suricata_rules,
        "-l",
        "/output",
        "-k",
        "none",
        "--set",
        f"outputs.1.eve-log.filename={eve_filename}",
    ]
    volumes = {
        str(project_root / "suricata"): {"bind": "/etc/suricata", "mode": "ro"},
        str(pcap_file.parent): {"bind": "/pcaps", "mode": "ro"},
        str(output_dir): {"bind": "/output", "mode": "rw"},
    }

    try:
        # Change rationale: use Docker SDK instead of shelling out to `docker run`.
        client.containers.run(
            image=suricata_image,
            command=command,
            remove=True,
            user=f"{os.getuid()}:{os.getgid()}",
            volumes=volumes,
        )
    except ContainerError as exc:
        error_log = output_dir / "suricata_offline_error.log"
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else str(exc.stderr)
        )
        error_log.write_text(
            f"PCAP: {pcap_file}\nSTDERR:\n{stderr}\n",
            encoding="utf-8",
        )
        raise RuntimeError(
            f"Offline Suricata execution failed for {pcap_file}. See log: {error_log}"
        ) from exc
    except DockerException as exc:
        raise RuntimeError(f"Docker SDK failed while running Suricata: {exc}") from exc


def _load_alert_events(eve_output: Path) -> List[dict]:
    alerts: List[dict] = []
    if not eve_output.exists():
        return alerts

    with eve_output.open(encoding="utf-8") as file_obj:
        for line in file_obj:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "alert":
                alerts.append(event)

    eve_output.unlink()
    return alerts


def _write_alert_jsonl(alerts: List[dict], output_alert_file: Path) -> None:
    if not alerts:
        output_alert_file.write_text("", encoding="utf-8")
        return

    with output_alert_file.open("w", encoding="utf-8") as file_obj:
        for alert in alerts:
            file_obj.write(json.dumps(alert) + "\n")


def build_suricata_alerts_from_pcap(
    pcap_input: Path,
    output_alert_file: Path,
    project_root: Path,
    suricata_image: str,
    suricata_rules: str,
) -> None:
    """Build Suricata alerts from PCAP files

    Args:
        pcap_input (Path): the PCAP input file or directory (if directory, all .pcap files inside will be processed)
        output_alert_file (Path): the file where the generated alerts will be saved in JSONL format
        project_root (Path): the root directory of the project
        suricata_image (str): the Docker image to use for running Suricata
        suricata_rules (str): the path to the Suricata rules file inside the container

    Raises:
        FileNotFoundError: if the PCAP input is not found or if no .pcap files are found in the input directory
        RuntimeError: if an error occurs while running the Suricata command
    """
    pcap_input = pcap_input.resolve()
    project_root = project_root.resolve()
    output_alert_file = output_alert_file.resolve()
    output_alert_file.parent.mkdir(parents=True, exist_ok=True)

    output_dir = output_alert_file.parent

    if output_alert_file.exists():
        output_alert_file.unlink()

    all_alerts: List[dict] = []
    for pcap_file in _collect_pcap_files(pcap_input):
        eve_output = output_dir / f"eve_{pcap_file.stem}.json"
        _run_suricata_container(
            pcap_file=pcap_file,
            output_dir=output_dir,
            project_root=project_root,
            suricata_image=suricata_image,
            suricata_rules=suricata_rules,
            eve_filename=eve_output.name,
        )
        all_alerts.extend(_load_alert_events(eve_output))
        print(f"Processed {pcap_file}, found {len(all_alerts)} total alerts so far.")
        for a in all_alerts:
            a['timestamp'] = fix_timestamp_to_rome_iso(a['timestamp'])
        print(f"Alerts after timestamp fix: {len(all_alerts)}")

        # all_alerts.extend([
        # {**alert, "timestamp": fix_timestamp_to_rome_iso(alert["timestamp"])} 
        # for alert in _load_alert_events(eve_output) if "timestamp" in alert
        # ])

    print("Write Suricata alerts to:", output_alert_file)

    _write_alert_jsonl(all_alerts, output_alert_file)


def label_flows(
    flows: List[Dict[str, Any]],
    alerts: List[AlertRecord],
    attack_events: List[AttackEvent],
    match_window_sec: float,
) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise SystemExit("Missing dependency 'pandas'. Install experiments requirements.") from exc

    records: List[Dict[str, Any]] = []

    for flow in flows:
        matched_alerts = [
            alert for alert in alerts if _flow_matches_alert(flow=flow, alert=alert, time_window_sec=match_window_sec)
        ]

        overlapping_event = _find_overlapping_attack_event(flow=flow, events=attack_events)
        expected_attack = overlapping_event is not None
        predicted_attack = len(matched_alerts) > 0

        if matched_alerts:
            # Suricata fired: trust the alert for attack_type (rules are correct).
            attack_type = matched_alerts[0].attack_type
        elif expected_attack and overlapping_event is not None:
            # Flow overlaps attack window but no alert fired (FN): use explicit attack_type from lab_ready.
            attack_type = overlapping_event.attack_type or "none"
        else:
            attack_type = "none"

        flow_start, flow_end = _flow_time_bounds(flow)

        record = dict(flow)
        record["flow_start_utc"] = flow_start.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        record["flow_end_utc"] = flow_end.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        record["predicted_label"] = "attack" if predicted_attack else "benign"
        record["expected_label"] = "attack" if expected_attack else "benign"
        record["attack_type"] = attack_type
        record["matched_alert_count"] = len(matched_alerts)
        record["matched_alert_sids"] = ",".join(str(alert.sid) for alert in matched_alerts if alert.sid is not None)

        records.append(record)

    return pd.DataFrame(records)


def compute_detection_metrics(df: Any) -> Dict[str, Any]:
    expected = list(df["expected_label"])
    predicted = list(df["predicted_label"])
    pairs = list(zip(expected, predicted))
    tp = sum(1 for actual, guess in pairs if actual == "attack" and guess == "attack")
    tn = sum(1 for actual, guess in pairs if actual == "benign" and guess == "benign")
    fp = sum(1 for actual, guess in pairs if actual == "benign" and guess == "attack")
    fn = sum(1 for actual, guess in pairs if actual == "attack" and guess == "benign")

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    accuracy = (tp + tn) / len(pairs) if pairs else 0.0

    return {
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "total_flows": int(len(df)),
        "total_predicted_attack": sum(1 for value in predicted if value == "attack"),
        "total_expected_attack": sum(1 for value in expected if value == "attack"),
    }


def _overlaps_any_event(ts_start: datetime, ts_end: datetime, events: List[AttackEvent]) -> bool:
    for event in events:
        if ts_start <= event.end_utc and ts_end >= event.start_utc:
            return True
    return False


def _expected_sids_for_event(event: AttackEvent) -> List[int]:
    """Return expected SIDs for an event, requiring explicit metadata from lab_ready."""
    if event.expected_sids is not None:
        return [int(sid) for sid in event.expected_sids]
    # Ground truth MUST come from lab_ready IPC event; no fallback to derived values.
    return []


def _empty_sid_confusion() -> Dict[str, int]:
    return {"TP": 0, "FP": 0, "FN": 0}


def _classification_metrics(
    tp: int,
    tn: int,
    fp: int,
    fn: int,
) -> Dict[str, Any]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)

    return {
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
    }


def validate_alerts_against_events(
    alerts: List[AlertRecord],
    events: List[AttackEvent],
    window_pre_sec: float,
    window_post_sec: float,
    timeline_bin_sec: float,
) -> Dict[str, Any]:
    if timeline_bin_sec <= 0:
        raise ValueError("timeline_bin_sec must be > 0")

    event_results: List[EventValidationResult] = []
    detected_events = 0
    unexpected_sid_alerts_total = 0
    events_with_unexpected_sids = 0
    unexpected_sid_values: set[int] = set()
    confusion_by_sid: Dict[str, Dict[str, int]] = {}
    matched_alert_ids: set[int] = set()

    def expected_sids_at(timestamp: datetime) -> set[int]:
        active: set[int] = set()
        for active_event in events:
            active_start = active_event.start_utc - timedelta(seconds=window_pre_sec)
            active_end = active_event.end_utc + timedelta(seconds=window_post_sec)
            if active_start <= timestamp <= active_end:
                active.update(_expected_sids_for_event(active_event))
        return active

    for idx, event in enumerate(events, start=1):
        window_start = event.start_utc - timedelta(seconds=window_pre_sec)
        window_end = event.end_utc + timedelta(seconds=window_post_sec)

        expected_sids = _expected_sids_for_event(event)
        expected_sid_set = set(expected_sids)

        alerts_in_window = [a for a in alerts if window_start <= a.timestamp <= window_end]

        # Change rationale: surface and quantify unexpected SIDs within each attack window,
        # so scenario-specific validation can fail fast when cross-scenario detections appear.
        if expected_sid_set:
            matched_alerts = [a for a in alerts_in_window if a.sid in expected_sid_set]
        else:
            matched_alerts = alerts_in_window

        for alert in alerts_in_window:
            matched_alert_ids.add(id(alert))

        unexpected_alert_count = 0
        unexpected_sids_in_event: List[int] = []
        if expected_sid_set:
            unexpected_alerts = [
                a
                for a in alerts_in_window
                if a.sid is not None and a.sid not in expected_sids_at(a.timestamp)
            ]
            unexpected_alert_count = len(unexpected_alerts)
            unexpected_sids_in_event = sorted({int(a.sid) for a in unexpected_alerts if a.sid is not None})
            if unexpected_alert_count > 0:
                events_with_unexpected_sids += 1
                unexpected_sid_alerts_total += unexpected_alert_count
                unexpected_sid_values.update(unexpected_sids_in_event)

        # Change rationale: FN means no attack alert at all in the attack window.
        detected = len(alerts_in_window) > 0
        if detected:
            detected_events += 1

        for sid in expected_sids:
            key = str(sid)
            if any(alert.sid == sid for alert in matched_alerts):
                confusion_by_sid.setdefault(key, _empty_sid_confusion())["TP"] += 1
            elif not detected:
                confusion_by_sid.setdefault(key, _empty_sid_confusion())["FN"] += 1
        for sid in unexpected_sids_in_event:
            confusion_by_sid.setdefault(str(sid), _empty_sid_confusion())["FP"] += 1

        event_results.append(
            EventValidationResult(
                event_index=idx,
                scenario_id=event.scenario_id,
                instance=event.instance,
                expected_sids=expected_sids,
                matched_sids=sorted({int(a.sid) for a in matched_alerts if a.sid is not None}),
                unexpected_sids=unexpected_sids_in_event,
                detected=detected,
            )
        )

    missed_events = len(events) - detected_events
    event_recall = (detected_events / len(events)) if events else 0.0
    unmatched_alerts = [alert for alert in alerts if id(alert) not in matched_alert_ids]
    false_positive_alerts = [
        alert for alert in unmatched_alerts if alert.sid is not None and alert.sid not in unexpected_sid_values
    ]

    tp = detected_events
    fn = missed_events
    fp = unexpected_sid_alerts_total + len(false_positive_alerts)
    tn = 0
    metrics = _classification_metrics(tp=tp, tn=tn, fp=fp, fn=fn)

    validation_passed = fn == 0 and fp == 0
    unexpected_sid_alerts_total = unexpected_sid_alerts_total + len(false_positive_alerts)

    return {
        "validation_passed": validation_passed,
        "metrics": {
            "total_events": len(events),
            "detected_events": detected_events,
            "missed_events": missed_events,
            "alerts_total": len(alerts),
            "unexpected_alerts": unexpected_sid_alerts_total,
            "event_recall": event_recall,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "accuracy": metrics["accuracy"],
        },
        "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        "confusion_by_sid": dict(sorted(confusion_by_sid.items())),
        "per_event": [result.__dict__ for result in event_results],
    }


def _build_dataset_impl(
    pcap_input: Path,
    alert_file: Path,
    events_file: Path,
    out_csv: Path,
    out_parquet: Optional[Path],
    metrics_out: Path,
    match_window_sec: float,
) -> None:
    pcap_files = _collect_pcap_files(pcap_input)
    alerts = load_alerts(alert_file)
    attack_events = load_attack_events(events_file)

    flows = extract_flows(pcap_files)
    if not flows:
        raise ValueError("No flows extracted from PCAP files")

    df = label_flows(
        flows=flows,
        alerts=alerts,
        attack_events=attack_events,
        match_window_sec=match_window_sec,
    )

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    if out_parquet is not None:
        out_parquet.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_parquet, index=False)

    metrics = compute_detection_metrics(df)
    metrics["pcap_files"] = [str(path) for path in pcap_files]
    metrics["alerts_file"] = str(alert_file)
    metrics["events_file"] = str(events_file)
    metrics["dataset_csv"] = str(out_csv)
    if out_parquet is not None:
        metrics["dataset_parquet"] = str(out_parquet)

    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def build_alert_validation_report(
    alert_file: Path,
    output_file: Path,
    runner_summary_file: Path,
    window_pre_sec: float,
    window_post_sec: float,
    timeline_bin_sec: float,
) -> None:
    alerts = load_alerts(alert_file)
    events = load_attack_events_from_runner_summary(
        summary_file=runner_summary_file,
        only_success=True,
    )

    report = validate_alerts_against_events(
        alerts=alerts,
        events=events,
        window_pre_sec=window_pre_sec,
        window_post_sec=window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
    )
    report["alerts_file"] = str(alert_file)
    report["runner_summary_file"] = str(runner_summary_file)
    report["window_pre_sec"] = window_pre_sec
    report["window_post_sec"] = window_post_sec
    report["only_successful_events"] = True
    report["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Change rationale: keep validation strict and deterministic across parallel experiments.
    unexpected_alert_count = int(report.get("metrics", {}).get("unexpected_alerts", 0))
    if unexpected_alert_count > 0:
        raise RuntimeError(
            "Unexpected SIDs detected in attack windows "
            f"(unexpected_sid_alerts_total={unexpected_alert_count}). "
            "See validation report for details."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="IDS dataset pipeline from PCAP/Suricata/NFStream")


@app.command()
def build_attack_events(
    runner_summary: Path = typer.Option(..., help="Path to scenario-runner summary.json"),
    output: Path = typer.Option(..., help="Path to output attack_events.json"),
) -> None:
    """Create attack events JSON from scenario-runner summary.json."""
    build_attack_events_from_runner_summary(
        summary_file=runner_summary.expanduser().resolve(),
        output_file=output.expanduser().resolve(),
    )
    print(f"Attack events file written to: {output}")


@app.command()
def build_alerts(
    pcap_input: Path = typer.Option(..., help="PCAP file or directory containing .pcap files"),
    output: Path = typer.Option(..., help="Output alert_json path"),
    project_root: Path = typer.Option(".", help="Project root path containing the suricata/ folder"),
    suricata_image: str = typer.Option(cfg.get("paths.suricata_image"), help="Suricata Docker image"),
    suricata_rules: str = typer.Option(cfg.get("paths.suricata_rules"), help="Suricata rules path inside container"),
) -> None:
    """Generate Suricata alert output from PCAP files in offline readback mode."""
    build_suricata_alerts_from_pcap(
        pcap_input=pcap_input.expanduser().resolve(),
        output_alert_file=output.expanduser().resolve(),
        project_root=project_root.expanduser().resolve(),
        suricata_image=suricata_image,
        suricata_rules=suricata_rules,
    )
    print(f"Suricata alerts written to: {output}")


@app.command()
def build_dataset(
    pcap_input: Path = typer.Option(..., help="PCAP file or directory containing .pcap files"),
    alerts: Path = typer.Option(..., help="IDS alerts file"),
    attack_events: Path = typer.Option(..., help="Attack events JSON file"),
    out_csv: Path = typer.Option(..., help="Output CSV path"),
    out_parquet: Path = typer.Option(None, help="Optional output Parquet path"),
    metrics_out: Path = typer.Option(..., help="Output detection_metrics JSON path"),
    match_window_sec: float = typer.Option(cfg.get("timing.match_window_sec"), help="Temporal tolerance window for alert/flow matching"),
) -> None:
    """Extract NFStream flows, label with IDS alerts and attack windows, export CSV/Parquet."""
    _build_dataset_impl(
        pcap_input=pcap_input.expanduser().resolve(),
        alert_file=alerts.expanduser().resolve(),
        events_file=attack_events.expanduser().resolve(),
        out_csv=out_csv.expanduser().resolve(),
        out_parquet=out_parquet.expanduser().resolve() if out_parquet else None,
        metrics_out=metrics_out.expanduser().resolve(),
        match_window_sec=match_window_sec,
    )
    print(f"Dataset CSV written to: {out_csv}")
    if out_parquet:
        print(f"Dataset Parquet written to: {out_parquet}")
    print(f"Detection metrics written to: {metrics_out}")


@app.command()
def validate_alerts(
    alerts: Path = typer.Option(..., help="IDS alerts (.txt/.jsonl) path"),
    runner_summary: Path = typer.Option(..., help="Scenario-runner summary.json path"),
    output: Path = typer.Option(..., help="Output validation report JSON path"),
    window_pre_sec: float = typer.Option(cfg.get("timing.alert_window_pre_sec"), help="Seconds to include before event start for alert matching"),
    window_post_sec: float = typer.Option(cfg.get("timing.alert_window_post_sec"), help="Seconds to include after event end for alert matching"),
    timeline_bin_sec: float = typer.Option(cfg.get("timing.timeline_bin_sec"), help="Timeline bin size in seconds for TP/TN/FP/FN computation"),
) -> None:
    """Validate IDS alert timing against ground-truth attack windows."""
    build_alert_validation_report(
        alert_file=alerts.expanduser().resolve(),
        output_file=output.expanduser().resolve(),
        runner_summary_file=runner_summary.expanduser().resolve(),
        window_pre_sec=window_pre_sec,
        window_post_sec=window_post_sec,
        timeline_bin_sec=timeline_bin_sec,
    )
    print(f"Alert validation report written to: {output}")


if __name__ == "__main__":
    app()
