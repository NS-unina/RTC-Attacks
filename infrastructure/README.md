# Infrastructure Management

Multipass VM management for RTC-Attacks infrastructure with experimental replicability features.

## Overview

This directory contains tools to create and manage Ubuntu VMs using Multipass with:
- Bridged networking (static IP assignment)
- Configurable resources (RAM, disk, CPUs)
- Support for multiple instances (up to 6 VMs: 10.0.0.230-235)
- **Experimental replicability controls** (CPU, memory, network, disk I/O)
- Auto-provisioning (Docker, monitoring tools)
- Snapshot/restore for quick experiment rollback

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
VM_BASE_IP=10.0.0.230          # First VM IP (increments for each instance)
VM_GATEWAY=10.0.0.1            # Network gateway
VM_BRIDGE_INTERFACE=enp3s0     # Host bridge interface name

# Resources (per VM)
VM_RAM=4G                      # RAM (4GB for multi-instance testing)
VM_DISK=60G                    # Disk size
VM_CPUS=8                      # CPU cores

# Replicability settings (applied via cloud-init)
VM_DISABLE_SWAP=true           # Disable swap for consistent performance
VM_MEMORY_OVERCOMMIT=2         # Memory overcommit mode (2=never)

# Network QoS (leave empty for unlimited, applied via cloud-init)
VM_NETWORK_BANDWIDTH_LIMIT=    # Bandwidth in Mbit/s
VM_NETWORK_LATENCY=            # Latency in ms
VM_NETWORK_PACKET_LOSS=        # Packet loss percentage

# Timezone and NTP (configured via cloud-init)
VM_TIMEZONE=Europe/Rome        # Timezone for consistent logging
VM_NTP_SERVERS=pool.ntp.org    # NTP servers for time sync

# Instance range
VM_MAX_INSTANCES=5             # Max instances (0-5 = 6 VMs)
```

**Cloud-init template:** `cloud-init.yaml` is a template file. During VM creation, the Makefile:
1. Copies the template to `/tmp/`
2. Substitutes variables like `{{VM_IP}}`, `{{VM_GATEWAY}}`, `{{VM_NAME}}`
3. Generates network QoS commands if configured
4. Passes the generated file to multipass

This ensures each VM gets the correct IP, network settings, and QoS configuration automatically.

## Usage

### Quick Start (Recommended)

Create a VM with all-in-one setup (create + sync code + install deps):
```bash
make setup-vm              # Creates rtc-vm-0, syncs code, installs dependencies
make setup-vm instance=1   # Same for rtc-vm-1
```

Then connect and run experiments:
```bash
make shell instance=0
# Inside VM:
rtc                        # Activate environment
make exp1-baseline SCENARIOS=1 MONITORING=on REPETITIONS=3
```

### Manual Workflow

If you prefer step-by-step:

**1. Create VM** (provisions via cloud-init: Docker, Python, network, etc.):
```bash
make create                # Creates rtc-vm-0 at 10.0.0.230
make create instance=1     # Creates rtc-vm-1 at 10.0.0.231
```

**2. Mount code** (live mounting of experiments, labs, database, scripts):
```bash
make mount-code instance=0
```

To unmount when done:
```bash
make unmount-code instance=0
```

**3. Install dependencies** (pip install requirements.txt in venv):
```bash
make install-deps instance=0
```

**4. Connect and run**:
```bash
make shell instance=0
# Inside VM:
rtc  # Activates venv and sets PYTHONPATH
make exp1-baseline SCENARIOS=1 MONITORING=on REPETITIONS=3
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

### Snapshot Management (for Experiment Rollback)

Create snapshot before experiment:
```bash
make snapshot instance=0 name=baseline
make snapshot instance=1 name=pre-experiment
```

Restore to baseline state:
```bash
make restore instance=0 name=baseline
```

### Monitoring and Testing

Show resource usage:
```bash
make show-stats instance=0
```

Run stress test (validates resource isolation):
```bash
make stress-test instance=0  # Runs 60s stress test
```

Re-provision VM (reinstall packages, reapply settings):
```bash
make provision instance=0
```

## Experimental Replicability Features

### What Cloud-Init Configures

The `cloud-init.yaml` template automatically provisions each VM with:

**System Configuration:**
- Static IP address (from `VM_BASE_IP` + instance number)
- Network gateway and DNS (from `VM_GATEWAY`)
- Timezone and NTP sync (from `VM_TIMEZONE`)
- Swap disabled (from `VM_DISABLE_SWAP`)
- Memory overcommit policy (from `VM_MEMORY_OVERCOMMIT`)

**Software Installation:**
- Docker & Docker Compose
- Python 3 with venv at `/home/ubuntu/rtcattack/.venv`
- Monitoring tools: sysstat, htop, iotop, iftop, nethogs, stress-ng
- Network tools: tcpdump, iproute2, net-tools
- Utilities: git, curl, wget, jq, tmux

**Network QoS (if configured):**
- Bandwidth limiting via `tc` (from `VM_NETWORK_BANDWIDTH_LIMIT`)
- Latency injection (from `VM_NETWORK_LATENCY`)
- Packet loss simulation (from `VM_NETWORK_PACKET_LOSS`)

**Kernel Tuning:**
- TCP buffer sizes optimized for RTC traffic
- Network core buffer sizes increased
- Memory overcommit disabled for strict allocation

**User Environment:**
- Activation script: `/home/ubuntu/rtcattack/activate.sh`
- Alias `rtc` added to bashrc
- Docker group membership for ubuntu user

### CPU Isolation
For consistent CPU performance across experiments:
- Set `VM_CPUS` to dedicated core count
- Future: Enable `VM_CPU_PINNING=true` for core isolation

### Memory Control
- `VM_DISABLE_SWAP=true`: Prevents swap-related performance variance
- `VM_MEMORY_OVERCOMMIT=2`: Prevents memory overcommitment (strict allocation)
- Fixed RAM allocation (4GB per VM) ensures predictable memory behavior

### Network Consistency
Control network conditions for reproducible scenarios:

```bash
# vm-config.env
VM_NETWORK_BANDWIDTH_LIMIT=100   # Limit to 100 Mbit/s
VM_NETWORK_LATENCY=10            # Add 10ms latency
VM_NETWORK_PACKET_LOSS=0.5       # 0.5% packet loss
```

Useful for testing RTC behavior under constrained networks.

### Time Synchronization
- All VMs sync to `VM_NTP_SERVERS`
- Timezone set to `VM_TIMEZONE` for consistent log timestamps
- Critical for correlating events across distributed experiments

### Monitoring Tools
Auto-installed on each VM when `VM_INSTALL_MONITORING=true`:
- **sysstat**: sar, iostat, mpstat for historical metrics
- **htop/iotop**: Real-time CPU/disk monitoring
- **iftop/nethogs**: Network monitoring
- **stress-ng**: Synthetic workload generation

Access via:
```bash
make shell instance=0
# Then inside VM:
htop           # CPU/memory usage
iotop -o       # Disk I/O
iftop -i ens4  # Network traffic
```

### Docker Pre-installed
When `VM_INSTALL_DOCKER=true`:
- Docker and docker-compose installed automatically
- User added to docker group (no sudo needed)
- Ready to deploy lab containers immediately

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

## Experimental Workflow Example

### Setup: Create baseline infrastructure
```bash
# Edit vm-config.env to set resources
make create-all              # Create all 6 VMs
make provision-all           # Ensure all provisioned
make snapshot instance=0 name=baseline  # Snapshot each
make snapshot instance=1 name=baseline
# ... repeat for all instances
```

### Run: Execute experiments
```bash
# SSH into VM and run experiments
make shell instance=0
# Inside VM: deploy containers, run scenarios

# Monitor from host
make show-stats instance=0
```

### Repeat: Rollback for next experiment
```bash
make restore instance=0 name=baseline  # Fast rollback
make restore instance=1 name=baseline
# VMs now in clean state, ready for next run
```

### Parallel Testing
Run multiple scenarios simultaneously across VMs:
```bash
# Terminal 1: Run scenario on VM-0
make shell instance=0
# run experiment...

# Terminal 2: Run scenario on VM-1
make shell instance=1
# run experiment...

# Each VM has 4GB RAM, 8 CPUs - isolated resources
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
- The network interface in the VM might not be called `ens4`
- SSH into VM and check: `ip link show`
- Adjust the interface name in the Makefile if needed

**Cloud-init not running:**
- Check logs inside VM: `make shell instance=0`, then `cat /var/log/cloud-init.log`
- Verify cloud-init completed: `ls /var/log/cloud-init-complete`

**Network QoS not working:**
- Ensure `tc` (traffic control) is available in VM
- Check current qdisc: `make shell instance=0`, then `tc qdisc show dev ens4`

## Resource Planning

### Single VM
- RAM: 4GB
- Disk: 60GB
- CPUs: 8 cores
- Host requirements: ~6GB RAM (VM + overhead)

### All 6 VMs
- Total RAM: 24GB (6 × 4GB)
- Total Disk: 360GB
- Total CPUs: 48 cores allocated (can overcommit)
- Host requirements: ~32GB RAM recommended

## Architecture

- `Makefile`: VM management automation
- `vm-config.env`: Configuration file (sourced by Makefile)
- `README.md`: Documentation (this file)
- VMs are named: `rtc-vm-0`, `rtc-vm-1`, ..., `rtc-vm-5`
- IPs: 10.0.0.230, 10.0.0.231, ..., 10.0.0.235

## Advanced: Custom Cloud-Init

For advanced provisioning, create a custom cloud-init file and reference it:

```bash
# vm-config.env
VM_CLOUD_INIT_FILE=/path/to/custom-cloud-init.yaml
```

The Makefile will use this instead of the auto-generated config.
