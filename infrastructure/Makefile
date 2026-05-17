# Multipass VM Infrastructure Management
# Manages VM instances with bridged networking and static IPs

-include vm-config.env

# Derived variables
VM_NAME = $(VM_NAME_PREFIX)-$(instance)
VM_IP = $(shell echo $(VM_BASE_IP) | awk -F. '{print $$1"."$$2"."$$3"."$$4+$(instance)}')

# Default instance (creates VM at 10.0.0.230)
instance ?= 0

.PHONY: help create delete start stop shell list info create-all delete-all check-multipass

help:
	@echo "Multipass VM Management"
	@echo ""
	@echo "Configuration is loaded from vm-config.env"
	@echo "Default VM: $(VM_NAME_PREFIX)-0 at $(VM_BASE_IP)"
	@echo ""
	@echo "Single instance commands (use instance=N to specify):"
	@echo "  make create [instance=N]  - Create VM instance N"
	@echo "  make delete [instance=N]  - Delete VM instance N"
	@echo "  make start [instance=N]   - Start VM instance N"
	@echo "  make stop [instance=N]    - Stop VM instance N"
	@echo "  make shell [instance=N]   - Open shell in VM instance N"
	@echo "  make info [instance=N]    - Show VM instance N details"
	@echo ""
	@echo "Batch commands:"
	@echo "  make create-all           - Create all configured VMs (0 to $(VM_MAX_INSTANCES))"
	@echo "  make delete-all           - Delete all VMs"
	@echo "  make list                 - List all multipass VMs"
	@echo ""
	@echo "Examples:"
	@echo "  make create               - Create rtc-vm-0 at 10.0.0.230"
	@echo "  make create instance=1    - Create rtc-vm-1 at 10.0.0.231"
	@echo "  make shell instance=2     - Shell into rtc-vm-2"

check-multipass:
	@command -v multipass >/dev/null 2>&1 || { echo "Error: multipass not installed"; exit 1; }

create: check-multipass
	@echo "[*] Creating VM: $(VM_NAME) with IP $(VM_IP)"
	@echo "[*] Resources: RAM=$(VM_RAM) DISK=$(VM_DISK) CPUS=$(VM_CPUS)"
	multipass launch $(VM_IMAGE) \
		--name $(VM_NAME) \
		--memory $(VM_RAM) \
		--disk $(VM_DISK) \
		--cpus $(VM_CPUS) \
		--network name=$(VM_BRIDGE_INTERFACE),mode=manual
	@echo "[*] Configuring static IP $(VM_IP)/$(VM_NETMASK)..."
	@sleep 3
	@multipass exec $(VM_NAME) -- sudo bash -c "\
		cat > /etc/netplan/60-static.yaml <<'EOF'\n\
		network:\n\
		  version: 2\n\
		  ethernets:\n\
		    extra0:\n\
		      addresses: [$(VM_IP)/$(VM_NETMASK)]\n\
		      routes:\n\
		        - to: default\n\
		          via: $(VM_GATEWAY)\n\
		      nameservers:\n\
		        addresses: [8.8.8.8, 1.1.1.1]\n\
		EOF\n\
		netplan apply"
	@echo "[+] VM $(VM_NAME) created and configured at $(VM_IP)"

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

create-all: check-multipass
	@echo "[*] Creating all VMs (instances 0 to $(VM_MAX_INSTANCES))"
	@for i in $$(seq $(VM_START_INDEX) $(VM_MAX_INSTANCES)); do \
		$(MAKE) create instance=$$i || exit 1; \
	done
	@echo "[+] All VMs created successfully"

delete-all: check-multipass
	@echo "[*] Deleting all VMs matching pattern $(VM_NAME_PREFIX)-*"
	@multipass list --format csv | tail -n +2 | cut -d, -f1 | grep "^$(VM_NAME_PREFIX)-" | xargs -r -I {} multipass delete {} --purge
	@echo "[+] All VMs deleted"

# Utility target to show current configuration
show-config:
	@echo "Current Configuration:"
	@echo "  VM_NAME_PREFIX     = $(VM_NAME_PREFIX)"
	@echo "  VM_BASE_IP         = $(VM_BASE_IP)"
	@echo "  VM_BRIDGE_INTERFACE= $(VM_BRIDGE_INTERFACE)"
	@echo "  VM_RAM             = $(VM_RAM)"
	@echo "  VM_DISK            = $(VM_DISK)"
	@echo "  VM_CPUS            = $(VM_CPUS)"
	@echo "  VM_MAX_INSTANCES   = $(VM_MAX_INSTANCES)"
	@echo "  VM_IMAGE           = $(VM_IMAGE)"
