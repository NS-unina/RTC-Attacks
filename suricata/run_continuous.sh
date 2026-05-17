#!/bin/bash
set -euo pipefail

# -----------------------------------------------------------------------------
# Continuous capture runner for RTC-Attacks with Suricata
# -----------------------------------------------------------------------------
# Change rationale: migrated from Snort 3 to Suricata for better offline PCAP
# analysis support and tolerance of invalid checksums from kernel TCP/UDP offload.

# Change rationale: capture root folder should reflect host local time for easier correlation.
SESSION_TAG="$(date +'%Y-%m-%d_%H-%M-%S')"
ROOT="/captures/${SESSION_TAG}"
PCAP_DIR="${ROOT}/pcap"
SURICATA_DIR="${ROOT}/suricata"
META_DIR="${ROOT}/meta"
LOG_DIR="${ROOT}/logs"

CAPTURE_MODE="${CAPTURE_MODE:-bridge_events}"
PCAP_ROTATE_SEC="${PCAP_ROTATE_SEC:-300}"
MONITOR_INTERVAL_SEC="${MONITOR_INTERVAL_SEC:-2}"

CAPTURE_PIDS=""
KNOWN_INTERFACES=""
DOCKER_EVENTS_PID=""
EVENT_FIFO=""

mkdir -p "${PCAP_DIR}" "${SURICATA_DIR}" "${META_DIR}" "${LOG_DIR}"
ln -sfn "${ROOT}" /captures/latest

echo "captures/${SESSION_TAG}" > /captures/last_root.txt

meta_info() {
    ip -o link > "${META_DIR}/host_links.txt" || true
    ip -o addr > "${META_DIR}/host_addrs.txt" || true
    docker ps --format '{{.ID}} {{.Names}} {{.Status}}' > "${META_DIR}/containers_snapshot.txt" || true
}

cleanup() {
    local exit_code="$?"
    echo "[suricata-runner] shutdown requested, cleaning up..."

    if [ -n "${DOCKER_EVENTS_PID}" ] && kill -0 "${DOCKER_EVENTS_PID}" 2>/dev/null; then
        kill "${DOCKER_EVENTS_PID}" 2>/dev/null || true
        wait "${DOCKER_EVENTS_PID}" 2>/dev/null || true
    fi

    if [ -n "${CAPTURE_PIDS// /}" ]; then
        local pid
        for pid in ${CAPTURE_PIDS}; do
            if kill -0 "${pid}" 2>/dev/null; then
                kill "${pid}" 2>/dev/null || true
                wait "${pid}" 2>/dev/null || true
            fi
        done
    fi

    if [ -n "${EVENT_FIFO}" ] && [ -p "${EVENT_FIFO}" ]; then
        rm -f "${EVENT_FIFO}" || true
    fi

    date -u +'%Y-%m-%dT%H:%M:%SZ' > "${ROOT}/stopped_at_utc.txt"
    echo "[suricata-runner] session root: ${ROOT}"
    exit "${exit_code}"
}

trap cleanup SIGINT SIGTERM EXIT

meta_info

echo "[suricata-runner] session root: ${ROOT}"
echo "[suricata-runner] pcap rotation: ${PCAP_ROTATE_SEC}s"
echo "[suricata-runner] capture mode: ${CAPTURE_MODE}"
echo "[suricata-runner] detection mode: offline Suricata on saved PCAP files"

_contains_iface() {
    local needle="$1"
    case " ${KNOWN_INTERFACES} " in
        *" ${needle} "*) return 0 ;;
        *) return 1 ;;
    esac
}

_capture_file_prefix() {
    local iface="$1"
    echo "${iface}" | tr -c '[:alnum:]_-' '_'
}

_start_capture_on_iface() {
    local iface="$1"
    local prefix
    prefix="$(_capture_file_prefix "${iface}")"

    echo "[suricata-runner] starting tcpdump on ${iface}"
    tcpdump -i "${iface}" \
        -s 0 \
        -U \
        -n \
        -Z root \
        -G "${PCAP_ROTATE_SEC}" \
        -w "${PCAP_DIR}/${prefix}_%Y%m%d_%H%M%S.pcap" \
        >> "${LOG_DIR}/tcpdump.log" 2>&1 &

    CAPTURE_PIDS="${CAPTURE_PIDS} $!"
    KNOWN_INTERFACES="${KNOWN_INTERFACES} ${iface}"
}

_discover_bridge_ifaces() {
    ip -o link \
        | awk -F': ' '{print $2}' \
        | awk -F':' '{print $1}' \
        | grep -E '^(br-|docker0$)' || true
}

_refresh_bridge_captures() {
    local found_any="false"
    local iface
    while IFS= read -r iface; do
        [ -n "${iface}" ] || continue
        found_any="true"

        if ! ip link show "${iface}" >/dev/null 2>&1; then
            continue
        fi

        if ! _contains_iface "${iface}"; then
            _start_capture_on_iface "${iface}"
        fi
    done < <(_discover_bridge_ifaces)

    if [ "${found_any}" = "false" ] && [ -z "${CAPTURE_PIDS// /}" ]; then
        echo "[suricata-runner] no bridge interface found yet; waiting..."
    fi
}

_start_docker_events_producer() {
    if [ -n "${DOCKER_EVENTS_PID}" ] && kill -0 "${DOCKER_EVENTS_PID}" 2>/dev/null; then
        return 0
    fi

    if [ -z "${EVENT_FIFO}" ]; then
        EVENT_FIFO="${ROOT}/docker_events.fifo"
    fi

    if [ ! -p "${EVENT_FIFO}" ]; then
        rm -f "${EVENT_FIFO}" || true
        mkfifo "${EVENT_FIFO}"
    fi

    docker events \
        --filter type=network \
        --format '{{.Action}} {{.Actor.Attributes.name}}' \
        > "${EVENT_FIFO}" 2>> "${LOG_DIR}/docker_events.log" &
    DOCKER_EVENTS_PID="$!"
    echo "[suricata-runner] docker events producer started pid=${DOCKER_EVENTS_PID}"
}

if [ "${CAPTURE_MODE}" = "bridge_events" ]; then
    echo "[suricata-runner] bridge_events enabled: event-driven docker bridge capture"
    _refresh_bridge_captures
    _start_docker_events_producer

    while true; do
        local_event=""
        if read -r -t "${MONITOR_INTERVAL_SEC}" local_event < "${EVENT_FIFO}"; then
            if [ -n "${local_event}" ]; then
                echo "[suricata-runner] docker network event: ${local_event}"
            fi
            _refresh_bridge_captures
        else
            _refresh_bridge_captures
        fi

        if [ -n "${DOCKER_EVENTS_PID}" ] && ! kill -0 "${DOCKER_EVENTS_PID}" 2>/dev/null; then
            echo "[suricata-runner] docker events producer stopped, restarting"
            _start_docker_events_producer
        fi
    done
else
    echo "[suricata-runner] fallback mode: single-interface capture on any"
    tcpdump -i any \
        -s 0 \
        -U \
        -n \
        -G "${PCAP_ROTATE_SEC}" \
        -w "${PCAP_DIR}/traffic_%Y%m%d_%H%M%S.pcap" \
        > "${LOG_DIR}/tcpdump.log" 2>&1 &
    TCPDUMP_PID="$!"
    wait "${TCPDUMP_PID}"
fi
