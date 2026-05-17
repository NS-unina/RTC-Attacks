STACK_ID := 9_firefox_access_cam_web
DRY_RUN_TAG := RTC_DRY_RUN
SCENARIO ?= 9
ATTACK_TYPE := permission_abuse
EXPECTED_SIDS := 2000009
DISABLE_SHARED_LIFECYCLE_TARGETS := 1
include ../shared.mk

SERVICE ?=
NET_PREFIX ?= 10.19.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
VICTIM_IP ?= $(NET_PREFIX).10
GOPHISH_IP ?= $(NET_PREFIX).11
FIREFOX_IP ?= $(NET_PREFIX).12
ATTACKER_IP ?= $(NET_PREFIX).100
NODE_HTTP_PORT ?= $(if $(filter 0,$(INSTANCE_INDEX)),80,808$(INSTANCE_INDEX))
GOPHISH_ADMIN_PORT ?= $(if $(filter 0,$(INSTANCE_INDEX)),3333,333$(INSTANCE_INDEX))
GOPHISH_PHISH_PORT ?= $(if $(filter 0,$(INSTANCE_INDEX)),81,81$(INSTANCE_INDEX))
GOPHISH_DB_PATH ?= $(if $(filter default,$(INSTANCE)),./gophish/data/gophish.db,./gophish/data/gophish-$(INSTANCE).db)
CAPTURE_PROOF_FILE ?= /app/data/audio/auto_attack_probe.webm
ATTACKER_IMAGE ?= curlimages/curl:8.8.0

export LAB_SUBNET VICTIM_IP GOPHISH_IP FIREFOX_IP ATTACKER_IP NODE_HTTP_PORT GOPHISH_ADMIN_PORT GOPHISH_PHISH_PORT GOPHISH_DB_PATH ATTACKER_IMAGE

prepare-instance:
	@mkdir -p ./gophish/data
	@if [ ! -f "$(GOPHISH_DB_PATH)" ]; then \
		echo "[*] Creating isolated GoPhish database at $(GOPHISH_DB_PATH)"; \
		cp ./gophish/data/gophish.db "$(GOPHISH_DB_PATH)"; \
	fi

run: prepare-instance
	@$(COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(COMPOSE) down --remove-orphans

start-node:
	# Previous implementation kept for traceability:
	# @docker exec -it node bash
	# Change rationale: service-scoped exec targets the selected Compose project instance and service name.
	@$(COMPOSE) exec node_firefox bash

build:
	@$(COMPOSE) build --no-cache $(SERVICE)
rebuild:
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)


dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@curl -fsS http://127.0.0.1:$(NODE_HTTP_PORT)/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=node_firefox_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=node_firefox_http"
	@curl -kfsS https://127.0.0.1:$(GOPHISH_ADMIN_PORT)/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=gophish_admin reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=gophish_admin"
	@$(COMPOSE) exec -T firefox sh -lc 'command -v firefox >/dev/null && test -n "$$DISPLAY" && test -d /tmp/.X11-unix' || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=firefox_gui_prereqs reason=missing_display_or_binary"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=firefox_gui_prereqs"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

capture-clean:
	@$(COMPOSE) exec -T node_firefox sh -lc "rm -f '$(CAPTURE_PROOF_FILE)'"

capture-attack:
	@echo "[*] Submitting proof audio capture to node_firefox from dedicated attacker..."
	@$(COMPOSE) exec -T attacker sh -c "curl -fsS -X POST \
		-H 'Content-Type: application/json' \
		-d '{\"audio\":\"data:audio/webm;base64,T2dnUw==\"}' \
		http://node_firefox:80/save-capture" >/tmp/lab9-capture.out

verify-capture:
	@$(COMPOSE) exec -T node_firefox sh -lc "ls -1 /app/data/audio/audio_*.webm >/dev/null 2>&1" || { \
		echo "[!] No captured audio file was written."; \
		exit 1; \
	}
	@echo "[+] Audio capture storage verified."

auto-attack: stop build start
	@$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) \
		expected_sids=$(EXPECTED_SIDS) attack_type=$(ATTACK_TYPE) \
		attacker_ip=$(ATTACKER_IP) victim_ip=$(VICTIM_IP) \
		probe_targets=$(ATTACKER_IP),$(VICTIM_IP) probe_protocols=tcp
	@echo "[*] Waiting for node_firefox and gophish readiness (8 seconds)..."
	@sleep 8
	@$(MAKE) attack
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)

attack:
	@echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
	@$(MAKE) capture-attack
	@echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
	@$(MAKE) verify-capture
