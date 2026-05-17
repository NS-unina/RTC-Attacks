# Infrastructure Management

Multipass VM management for RTC-Attacks infrastructure.

## Overview

This directory contains tools to create and manage Ubuntu VMs using Multipass with:
- Bridged networking (static IP assignment)
- Configurable resources (RAM, disk, CPUs)
- Support for multiple instances (up to 6 VMs: 10.0.0.230-235)

## Prerequisites

Install Multipass:
```bash
# Ubuntu/Debian
sudo snap install multipass

# macOS
brew install multipass
```

## Configuration

Edit `vm-config.env` to customize VM settings:

```bash
# Network configuration
VM_BASE_IP=10.0.0.230          # First VM IP
VM_GATEWAY=10.0.0.1            # Network gateway
VM_BRIDGE_INTERFACE=enp3s0     # Host bridge interface name

# Resources
VM_RAM=32G                     # RAM per VM
VM_DISK=60G                    # Disk size per VM
VM_CPUS=8                      # CPU cores per VM

# Instance range
VM_MAX_INSTANCES=5             # Max instances (0-5 = 6 VMs)
```

## Usage

### Single VM Management

Create the default VM (instance 0 at 10.0.0.230):
```bash
make create
```

Create a specific instance:
```bash
make create instance=1  # Creates rtc-vm-1 at 10.0.0.231
make create instance=2  # Creates rtc-vm-2 at 10.0.0.232
```

Manage VMs:
```bash
make start instance=0   # Start VM
make stop instance=0    # Stop VM
make shell instance=0   # Open shell
make info instance=0    # Show VM details
make delete instance=0  # Delete VM
```

### Batch Operations

Create all configured VMs:
```bash
make create-all  # Creates instances 0-5 (10.0.0.230-235)
```

Delete all VMs:
```bash
make delete-all
```

List all VMs:
```bash
make list
```

Show current configuration:
```bash
make show-config
```

## Network Setup

The VMs use bridged networking with static IP assignment. Ensure:

1. The bridge interface exists on your host (`VM_BRIDGE_INTERFACE`)
2. The IP range (10.0.0.230-235) is available
3. Gateway and DNS are reachable from that network

To find your bridge interface:
```bash
ip link show
# or
networkctl list
```

## Examples

### Create single VM for testing
```bash
# Edit vm-config.env first, then:
make create
make shell  # Access the VM
```

### Create full infrastructure (6 VMs)
```bash
make create-all
make list  # Verify all VMs are running
```

### Cleanup
```bash
make delete-all  # Remove all VMs
```

## Troubleshooting

**VM creation fails:**
- Check multipass is installed: `multipass version`
- Verify bridge interface name in vm-config.env
- Ensure IP range is available

**Network not working:**
- Check gateway is correct: `ping -c 1 <VM_GATEWAY>`
- Verify bridge interface: `ip link show <VM_BRIDGE_INTERFACE>`
- Check VM network config: `make shell instance=0`, then `ip addr`

**Netplan apply fails:**
- The network interface in the VM might not be called `extra0`
- SSH into VM and check: `ip link show`
- Adjust the interface name in the Makefile if needed

## Architecture

- `Makefile`: VM management automation
- `vm-config.env`: Configuration file (sourced by Makefile)
- VMs are named: `rtc-vm-0`, `rtc-vm-1`, ..., `rtc-vm-5`
- IPs: 10.0.0.230, 10.0.0.231, ..., 10.0.0.235
