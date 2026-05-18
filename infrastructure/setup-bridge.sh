#!/bin/bash
# Setup custom bridge network for RTC-Attacks VMs
# Network: 10.30.0.0/24
# Gateway: 10.30.0.1
# VMs: 10.30.0.10 - 10.30.0.20

set -e

BRIDGE_NAME="br-rtc"
BRIDGE_IP="10.30.0.1"
BRIDGE_SUBNET="10.30.0.0/24"

echo "[*] Creating bridge network: $BRIDGE_NAME"

# Create bridge if it doesn't exist
if ! ip link show "$BRIDGE_NAME" &> /dev/null; then
    sudo ip link add name "$BRIDGE_NAME" type bridge
    echo "[+] Bridge $BRIDGE_NAME created"
else
    echo "[!] Bridge $BRIDGE_NAME already exists"
fi

# Configure bridge IP
sudo ip addr flush dev "$BRIDGE_NAME"
sudo ip addr add "$BRIDGE_IP/24" dev "$BRIDGE_NAME"
sudo ip link set "$BRIDGE_NAME" up

echo "[+] Bridge configured with IP $BRIDGE_IP"

# Enable IP forwarding
sudo sysctl -w net.ipv4.ip_forward=1
echo "[+] IP forwarding enabled"

# Setup NAT for VM internet access
sudo iptables -t nat -C POSTROUTING -s "$BRIDGE_SUBNET" -j MASQUERADE 2>/dev/null || \
    sudo iptables -t nat -A POSTROUTING -s "$BRIDGE_SUBNET" -j MASQUERADE

echo "[+] NAT configured for $BRIDGE_SUBNET"

# Make bridge persistent with netplan
NETPLAN_FILE="/etc/netplan/99-rtc-bridge.yaml"
if [ ! -f "$NETPLAN_FILE" ]; then
    echo "[*] Creating netplan configuration..."
    sudo tee "$NETPLAN_FILE" > /dev/null <<EOF
network:
  version: 2
  bridges:
    $BRIDGE_NAME:
      dhcp4: no
      addresses:
        - $BRIDGE_IP/24
EOF
    sudo chmod 600 "$NETPLAN_FILE"
    echo "[+] Netplan configuration created: $NETPLAN_FILE"
fi

echo ""
echo "[✓] Bridge network setup complete!"
echo ""
echo "Network details:"
echo "  Bridge: $BRIDGE_NAME"
echo "  Gateway: $BRIDGE_IP"
echo "  Subnet: $BRIDGE_SUBNET"
echo "  VM IPs: 10.30.0.10 - 10.30.0.20"
echo ""
echo "Next: Use 'multipass launch --network name=$BRIDGE_NAME,mode=manual' to connect VMs"
