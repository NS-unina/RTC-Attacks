# Multipass VM Infrastructure Management
# Manages VM instances with bridged networking and static IPs

-include vm-config.env

# Project root directory
PROJECT_ROOT := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))/../

# Derived variables
VM_NAME = $(VM_NAME_PREFIX)-$(instance)
VM_IP = $(shell echo $(VM_BASE_IP) | awk -F. '{print $$1"."$$2"."$$3"."$$4+$(instance)}')

# Default instance (creates VM at 10.0.0.230)
instance ?= 0

.PHONY: help create delete start stop shell list info create-all delete-all check-multipass \
        snapshot restore show-stats stress-test mount-code unmount-code install-deps setup-vm

help:
	@echo "Multipass VM Management"
	@echo ""
	@echo "Configuration is loaded from vm-config.env"
	@echo "Default VM: $(VM_NAME_PREFIX)-0 at $(VM_BASE_IP)"
	@echo ""
	@echo "Single instance commands (use instance=N to specify):"
	@echo "  make create [instance=N]   - Create VM instance N"
	@echo "  make setup-vm [instance=N] - Create + sync code + install deps (all-in-one)"
	@echo "  make setup-heavy-vm        - Create heavy VM at 10.30.0.15 (16GB RAM, instance=5)"
	@echo "  make mount-code [instance=N]- Mount RTC-Attacks code to VM (live editing)"
	@echo "  make unmount-code [instance=N]- Unmount directories from VM"
	@echo "  make install-deps [instance=N] - Install Python dependencies in VM"
	@echo "  make delete [instance=N]   - Delete VM instance N"
	@echo "  make start [instance=N]    - Start VM instance N"
	@echo "  make stop [instance=N]     - Stop VM instance N"
	@echo "  make shell [instance=N]    - Open shell in VM instance N"
	@echo "  make info [instance=N]     - Show VM instance N details"
	@echo ""
	@echo "Batch commands:"
	@echo "  make create-all            - Create all configured VMs (0 to $(VM_MAX_INSTANCES))"
	@echo "  make setup-all             - Create all VMs + sync + install deps"
	@echo "  make sync-all              - Sync code to all VMs"
	@echo "  make delete-all            - Delete all VMs"
	@echo "  make list                  - List all multipass VMs"
	@echo ""
	@echo "Snapshot management:"
	@echo "  make snapshot [instance=N] [name=NAME] - Create snapshot"
	@echo "  make restore [instance=N] [name=NAME]  - Restore from snapshot"
	@echo ""
	@echo "Monitoring and testing:"
	@echo "  make show-stats [instance=N]           - Show VM resource usage"
	@echo "  make stress-test [instance=N]          - Run stress test on VM"
	@echo ""
	@echo "Examples:"
	@echo "  make setup-vm              - Create rtc-vm-0, sync code, install deps"
	@echo "  make setup-vm instance=1   - Same for rtc-vm-1"
	@echo "  make shell instance=0      - Shell into rtc-vm-0"
	@echo "  make snapshot instance=0 name=baseline - Save baseline state"

setup-bridge:
	@echo "[*] Setting up custom bridge network: $(VM_BRIDGE)"
	@bash $(PROJECT_ROOT)infrastructure/setup-bridge.sh
	@echo "[+] Bridge network ready!"
	@echo "[+] Network: 10.30.0.0/24, Gateway: 10.30.0.1"

check-multipass:
	@command -v multipass >/dev/null 2>&1 || { echo "Error: multipass not installed"; exit 1; }

create: check-multipass setup-bridge
	@echo "[*] Creating VM: $(VM_NAME) with IP $(VM_IP)"
	@echo "[*] Resources: RAM=$(VM_RAM) DISK=$(VM_DISK) CPUS=$(VM_CPUS)"
	@echo "[*] Network: $(VM_BRIDGE) (10.30.0.0/24)"
	@echo "[*] Generating cloud-init with network configuration..."
	@$(MAKE) _generate-cloud-init instance=$(instance)
	@# Launch VM with custom bridge network and cloud-init
	@# Default NAT network (ens3) + custom bridge (extra0) for static IP
	@cat /tmp/$(VM_NAME)-cloud-init.yaml | multipass launch $(VM_IMAGE) \
		--name $(VM_NAME) \
		--memory $(VM_RAM) \
		--disk $(VM_DISK) \
		--cpus $(VM_CPUS) \
		--network name=$(VM_BRIDGE),mode=manual \
		--cloud-init -
	@echo "[*] Waiting for cloud-init to complete (this may take 2-3 minutes)..."
	@sleep 10
	@multipass exec $(VM_NAME) -- cloud-init status --wait || true
	@rm -f /tmp/$(VM_NAME)-cloud-init.yaml
	@echo "[+] VM $(VM_NAME) created and configured at $(VM_IP)"
	@echo "[+] Network, Docker, Python venv all configured via cloud-init"
	@echo "[+] VM $(VM_NAME) created and configured"
	@echo "[+] Static IP: $(VM_IP) on bridge $(VM_BRIDGE)"
	@echo "[+] Next: make mount-code instance=$(instance) to mount RTC-Attacks code"

_generate-cloud-init:
	@# Generate cloud-init from template with variable substitution
	@cp $(PROJECT_ROOT)infrastructure/cloud-init.yaml /tmp/$(VM_NAME)-cloud-init.yaml
	@# Substitute VM-specific variables
	@sed -i 's|{{VM_IP}}|$(VM_IP)|g' /tmp/$(VM_NAME)-cloud-init.yaml
	@sed -i 's|{{VM_NETMASK}}|$(VM_NETMASK)|g' /tmp/$(VM_NAME)-cloud-init.yaml
	@sed -i 's|{{VM_GATEWAY}}|$(VM_GATEWAY)|g' /tmp/$(VM_NAME)-cloud-init.yaml
	@sed -i 's|{{VM_NAME}}|$(VM_NAME)|g' /tmp/$(VM_NAME)-cloud-init.yaml
	@# Generate network QoS commands if configured
	@QOS_COMMANDS=""; \
	if [ -n "$(VM_NETWORK_BANDWIDTH_LIMIT)" ]; then \
		QOS_COMMANDS="$$QOS_COMMANDS  - tc qdisc add dev extra0 root tbf rate $(VM_NETWORK_BANDWIDTH_LIMIT)mbit burst 32kbit latency 400ms\n"; \
	fi; \
	if [ -n "$(VM_NETWORK_LATENCY)" ]; then \
		QOS_COMMANDS="$$QOS_COMMANDS  - tc qdisc add dev extra0 root netem delay $(VM_NETWORK_LATENCY)ms\n"; \
	fi; \
	if [ -n "$(VM_NETWORK_PACKET_LOSS)" ]; then \
		QOS_COMMANDS="$$QOS_COMMANDS  - tc qdisc add dev extra0 root netem loss $(VM_NETWORK_PACKET_LOSS)%\n"; \
	fi; \
	if [ -z "$$QOS_COMMANDS" ]; then \
		QOS_COMMANDS="  # No network QoS configured"; \
	fi; \
	echo "$$QOS_COMMANDS" | sed 's|\\n|\n|g' > /tmp/qos-commands.txt; \
	sed -i "/{{NETWORK_QOS_COMMANDS}}/r /tmp/qos-commands.txt" /tmp/$(VM_NAME)-cloud-init.yaml; \
	sed -i '/{{NETWORK_QOS_COMMANDS}}/d' /tmp/$(VM_NAME)-cloud-init.yaml; \
	rm -f /tmp/qos-commands.txt

mount-code: check-multipass
	@echo "[*] Mounting RTC-Attacks directories to VM: $(VM_NAME)"
	@echo "[*] This allows live code editing without sync"
	@# Create target directories in VM
	@multipass exec $(VM_NAME) -- sudo -u ubuntu mkdir -p /home/ubuntu/rtcattack/experiments
	@multipass exec $(VM_NAME) -- sudo -u ubuntu mkdir -p /home/ubuntu/rtcattack/public/labs
	@multipass exec $(VM_NAME) -- sudo -u ubuntu mkdir -p /home/ubuntu/rtcattack/database
	@multipass exec $(VM_NAME) -- sudo -u ubuntu mkdir -p /home/ubuntu/rtcattack/scripts
	@multipass exec $(VM_NAME) -- sudo -u ubuntu mkdir -p /home/ubuntu/rtcattack/logs
	@# Mount directories with proper UID/GID mapping (host 1000:1000 -> VM 1000:1001)
	@multipass mount $(PROJECT_ROOT)experiments $(VM_NAME):/home/ubuntu/rtcattack/experiments -u 1000:1000 -g 1000:1001
	@multipass mount $(PROJECT_ROOT)public/labs $(VM_NAME):/home/ubuntu/rtcattack/public/labs -u 1000:1000 -g 1000:1001
	@multipass mount $(PROJECT_ROOT)database $(VM_NAME):/home/ubuntu/rtcattack/database -u 1000:1000 -g 1000:1001
	@multipass mount $(PROJECT_ROOT)scripts $(VM_NAME):/home/ubuntu/rtcattack/scripts -u 1000:1000 -g 1000:1001
	@echo "[+] Directories mounted to $(VM_NAME):/home/ubuntu/rtcattack/"
	@echo "[+] Changes on host are immediately visible in VM"

unmount-code: check-multipass
	@echo "[*] Unmounting directories from VM: $(VM_NAME)"
	@multipass umount $(VM_NAME):/home/ubuntu/rtcattack/experiments || true
	@multipass umount $(VM_NAME):/home/ubuntu/rtcattack/public/labs || true
	@multipass umount $(VM_NAME):/home/ubuntu/rtcattack/logs || true
	@multipass umount $(VM_NAME):/home/ubuntu/rtcattack/database || true
	@multipass umount $(VM_NAME):/home/ubuntu/rtcattack/scripts || true
	@echo "[+] Directories unmounted from $(VM_NAME)"

install-deps: check-multipass
	@echo "[*] Installing Python dependencies in VM: $(VM_NAME)"
	@multipass exec $(VM_NAME) -- sudo -u ubuntu bash -c "\
		source /home/ubuntu/rtcattack/.venv/bin/activate && \
		cd /home/ubuntu/rtcattack/experiments && \
		pip install --upgrade pip && \
		pip install -r requirements.txt && \
		echo 'Dependencies installed successfully'"
	@echo "[+] Dependencies installed in $(VM_NAME)"

setup-vm: create mount-code install-deps
	@echo "[+] VM $(VM_NAME) fully configured and ready for experiments"
	@echo "[+] Connect with: make shell instance=$(instance)"
	@echo "[+] Or SSH to: $(VM_IP)"

# Special high-memory VM for heavy workloads (10.30.0.15, 16GB RAM)
setup-heavy-vm:
	@echo "[*] Creating heavy-duty VM at 10.30.0.15 with 16GB RAM"
	@$(MAKE) create instance=5 VM_RAM=16G VM_CPUS=8 VM_DISK=100G
	@$(MAKE) mount-code instance=5
	@$(MAKE) install-deps instance=5
	@echo "[+] Heavy VM rtc-vm-5 ready at 10.30.0.15"
	@echo "[+] Resources: 16GB RAM, 8 CPUs, 100GB disk"

sync-all: check-multipass
	@echo "[*] Syncing code to all VMs (instances 0 to $(VM_MAX_INSTANCES))"
	@for i in $$(seq $(VM_START_INDEX) $(VM_MAX_INSTANCES)); do \
		$(MAKE) mount-code instance=$$i || exit 1; \
	done
	@echo "[+] Code synced to all VMs"

setup-all: create-all sync-all
	@echo "[*] Installing dependencies on all VMs..."
	@for i in $$(seq $(VM_START_INDEX) $(VM_MAX_INSTANCES)); do \
		$(MAKE) install-deps instance=$$i || exit 1; \
	done
	@echo "[+] All VMs fully configured and ready"

delete: check-multipass
	@echo "[*] Deleting VM: $(VM_NAME)"
	multipass delete $(VM_NAME) --purge || true

start: check-multipass
	@echo "[*] Starting VM: $(VM_NAME)"
	multipass start $(VM_NAME)

stop: check-multipass
	@echo "[*] Stopping VM: $(VM_NAME)"
	multipass stop $(VM_NAME)

shell: check-multipass
	@echo "[*] Opening shell in VM: $(VM_NAME)"
	multipass shell $(VM_NAME)

info: check-multipass
	@echo "[*] VM Info: $(VM_NAME)"
	@multipass info $(VM_NAME)

list: check-multipass
	@multipass list

ls: list

create-all: check-multipass
	@echo "[*] Creating all VMs (instances 0 to $(VM_MAX_INSTANCES))"
	@for i in $$(seq $(VM_START_INDEX) $(VM_MAX_INSTANCES)); do \
		$(MAKE) create instance=$$i || exit 1; \
	done
	@echo "[+] All VMs created successfully"
	@echo "[+] Next: make mount-all to mount code to all VMs"

delete-all: check-multipass
	@echo "[*] Deleting all VMs matching pattern $(VM_NAME_PREFIX)-*"
	@multipass list --format csv | tail -n +2 | cut -d, -f1 | grep "^$(VM_NAME_PREFIX)-" | xargs -r -I {} multipass delete {} --purge
	@echo "[+] All VMs deleted"

snapshot: check-multipass
	@if [ -z "$(name)" ]; then \
		echo "Error: snapshot name required. Usage: make snapshot instance=N name=NAME"; \
		exit 1; \
	fi
	@echo "[*] Creating snapshot '$(name)' for VM: $(VM_NAME)"
	@multipass snapshot $(VM_NAME) --name $(name)
	@echo "[+] Snapshot created"

restore: check-multipass
	@if [ -z "$(name)" ]; then \
		echo "Error: snapshot name required. Usage: make restore instance=N name=NAME"; \
		exit 1; \
	fi
	@echo "[*] Restoring VM $(VM_NAME) from snapshot '$(name)'"
	@multipass restore $(VM_NAME).$(name)
	@echo "[+] Snapshot restored"

show-stats: check-multipass
	@echo "[*] Resource usage for VM: $(VM_NAME)"
	@multipass exec $(VM_NAME) -- bash -c "\
		echo '=== CPU Usage ==='; \
		mpstat 1 1 | tail -1; \
		echo ''; \
		echo '=== Memory Usage ==='; \
		free -h; \
		echo ''; \
		echo '=== Disk I/O ==='; \
		iostat -x 1 1 | tail -n +4; \
		echo ''; \
		echo '=== Network Stats ==='; \
		ip -s link show extra0 | grep -A1 'RX:'"

stress-test: check-multipass
	@echo "[*] Running stress test on VM: $(VM_NAME)"
	@echo "[*] This will run for 60 seconds..."
	@multipass exec $(VM_NAME) -- stress-ng --cpu $(VM_CPUS) --io 4 --vm 2 --vm-bytes 1G --timeout 60s --metrics-brief

# Utility target to show current configuration
show-config:
	@echo "Current Configuration:"
	@echo "  VM_NAME_PREFIX          = $(VM_NAME_PREFIX)"
	@echo "  VM_BASE_IP              = $(VM_BASE_IP)"
	@echo "  VM_BRIDGE_INTERFACE     = $(VM_BRIDGE_INTERFACE)"
	@echo "  VM_RAM                  = $(VM_RAM)"
	@echo "  VM_DISK                 = $(VM_DISK)"
	@echo "  VM_CPUS                 = $(VM_CPUS)"
	@echo "  VM_MAX_INSTANCES        = $(VM_MAX_INSTANCES)"
	@echo "  VM_IMAGE                = $(VM_IMAGE)"
	@echo "  VM_DISABLE_SWAP         = $(VM_DISABLE_SWAP)"
	@echo "  VM_MEMORY_OVERCOMMIT    = $(VM_MEMORY_OVERCOMMIT)"
	@echo "  VM_NETWORK_BANDWIDTH_LIMIT = $(VM_NETWORK_BANDWIDTH_LIMIT)"
	@echo "  VM_NETWORK_LATENCY      = $(VM_NETWORK_LATENCY)"
	@echo "  VM_TIMEZONE             = $(VM_TIMEZONE)"
	@echo ""
	@echo "Cloud-init: infrastructure/cloud-init.yaml"
	@echo "  - Installs Docker, Python3, monitoring tools"
	@echo "  - Creates venv at /home/ubuntu/rtcattack/.venv"
	@echo "  - Disables swap, sets timezone, configures kernel"
