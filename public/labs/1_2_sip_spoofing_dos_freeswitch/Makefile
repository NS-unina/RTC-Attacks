STACK_ID := 1_2_sip_spoofing_dos_freeswitch

include ../shared.mk
COMPOSE_PROJECT_NAME ?= $(STACK_ID)$(if $(filter default,$(INSTANCE)),,_$(INSTANCE))
COMPOSE := COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) $(DOCKER_COMPOSE)

NET_PREFIX ?= 10.12.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
FREESWITCH_IP ?= $(NET_PREFIX).5
ATTACKER_IP ?= $(NET_PREFIX).20
CLIENT_IP ?= $(NET_PREFIX).31
TARGET_IP ?= $(FREESWITCH_IP)
TARGET_EXT ?= 1001
SCENARIO ?= 1

# Ground truth metadata for IDS evaluation (scenario-specific)
ifeq ($(SCENARIO),1)
EXPECTED_SIDS := 2000001
ATTACK_TYPE := sip_spoofing
else ifeq ($(SCENARIO),2)
EXPECTED_SIDS := 2000002
ATTACK_TYPE := sip_register_flood
else
EXPECTED_SIDS := 
ATTACK_TYPE := 
endif

SIP_SERVER ?= $(TARGET_IP)
CLIENT_EXT ?= $(TARGET_EXT)
CLIENT_PASS ?= 1234
CLIENT_WAIT_SEC ?= 25
CLIENT_PORT ?= 5062
DOS_CHECK_TIMEOUT_SEC ?= 180
DOS_CHECK_INTERVAL_SEC ?= 2
DOS_MEM_LOG ?= /tmp/freeswitch-dos-mem.log
REPEAT_RUNS ?= 20
REPEAT_DELAY_SEC ?= 2
REPEAT_LOG ?= /tmp/lab12-repeat.log
REPEAT_MIN_SUCCESS ?= $(REPEAT_RUNS)

export LAB_SUBNET FREESWITCH_IP ATTACKER_IP CLIENT_IP SIP_SERVER CLIENT_EXT CLIENT_PASS CLIENT_PORT

start: stop 
	@$(COMPOSE) up -d --remove-orphans


attack: 
	@if [ "$(SCENARIO)" = "1" ]; then \
		$(MAKE) client-up SIP_SERVER="$(SIP_SERVER)" CLIENT_EXT="$(CLIENT_EXT)" CLIENT_PASS="$(CLIENT_PASS)"; \
		$(MAKE) client-wait-registered CLIENT_EXT="$(CLIENT_EXT)" CLIENT_WAIT_SEC="$(CLIENT_WAIT_SEC)"; \
		$(MAKE) spoof-attack TARGET_IP="$(TARGET_IP)" TARGET_EXT="$(TARGET_EXT)"; \
		sleep 2; \
		$(MAKE) client-check-spoof; \
	elif [ "$(SCENARIO)" = "2" ]; then \
		$(MAKE) dos-start TARGET_IP="$(TARGET_IP)"; \
		$(MAKE) dos-check; \
	else \
		echo "[!] Invalid SCENARIO=$(SCENARIO). Use 1 (spoofing) or 2 (dos)."; \
		exit 1; \
	fi
	$(MAKE) stop




dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID) scenario=$(SCENARIO)"
	@$(COMPOSE) exec -T attacker sh -lc "test -f /spoofing.py && test -f /dos-sipflood.py" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=attacker_scripts reason=missing_files"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=attacker_scripts"
	@$(COMPOSE) exec -T freeswitch sh -lc "fs_cli -x status >/dev/null" || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=freeswitch_status reason=fs_cli_unavailable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=freeswitch_status"
	@if [ "$(SCENARIO)" = "1" ]; then \
		i=0; \
		while [ $$i -lt "$(CLIENT_WAIT_SEC)" ]; do \
			if $(COMPOSE) logs sip-cli-1001 2>&1 | grep -q "REGISTER_OK"; then \
				echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=sip_cli_registered"; \
				echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) scenario=$(SCENARIO) ready=true"; \
				exit 0; \
			fi; \
			sleep 1; \
			i=$$((i+1)); \
		done; \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=sip_cli_registered reason=timeout"; \
		exit 1; \
	elif [ "$(SCENARIO)" = "2" ]; then \
		echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) scenario=$(SCENARIO) ready=true"; \
	else \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=scenario reason=invalid_scenario value=$(SCENARIO)"; \
		exit 1; \
	fi

spoof-attack:
	@echo "[*] Sending spoofed SIP MESSAGE to $(TARGET_EXT) via $(TARGET_IP)..."
	@$(COMPOSE) exec -T attacker python3 /spoofing.py "$(TARGET_IP)" "$(TARGET_EXT)"
	@echo "[+] Spoofing packet sent."

client-up:
	@echo "[*] Starting legit SIP client $(CLIENT_EXT) against $(SIP_SERVER)..."
	@SIP_SERVER="$(SIP_SERVER)" CLIENT_EXT="$(CLIENT_EXT)" CLIENT_PASS="$(CLIENT_PASS)" CLIENT_IP="$(CLIENT_IP)" CLIENT_PORT="$(CLIENT_PORT)" $(COMPOSE) up -d sip-cli-1001

client-logs:
	@$(COMPOSE) logs --tail 120 sip-cli-1001

client-watch:
	@$(COMPOSE) logs -f sip-cli-1001

client-wait-registered:
	@echo "[*] Waiting for registration success from SIP CLI (timeout: $(CLIENT_WAIT_SEC)s)..."
	@i=0; \
	while [ $$i -lt "$(CLIENT_WAIT_SEC)" ]; do \
		if $(COMPOSE) logs sip-cli-1001 2>&1 | grep -q "REGISTER_OK"; then \
			echo "[+] Client $(CLIENT_EXT) registered."; \
			exit 0; \
		fi; \
		sleep 1; \
		i=$$((i+1)); \
	done; \
	echo "[!] Client $(CLIENT_EXT) not registered within $(CLIENT_WAIT_SEC)s."; \
	echo "[i] Check with: make client-logs"; \
	exit 1

client-check-spoof:
	@echo "[*] Checking client log for spoofed UniCredit message..."
	@if $(COMPOSE) logs sip-cli-1001 2>&1 | grep -Eiq "\\[INCOMING_MESSAGE\\].*(UniCredit|withdrawal of|withdrawal)"; then \
		echo "[+] Spoofing evidence found in sip-cli-1001 logs."; \
	else \
		echo "[!] No spoofing evidence found in logs yet."; \
		echo "[i] Follow live logs with: make client-watch"; \
		exit 1; \
	fi

dos-start:
	@echo "[*] Starting SIP flood against $(TARGET_IP) in background..."
	@$(COMPOSE) exec -d attacker sh -lc "python3 /dos-sipflood.py '$(TARGET_IP)' >/tmp/dos.log 2>&1"
	@echo "[+] DoS flood started. Use 'make dos-stop' to stop it."

dos-stop:
	@echo "[*] Stopping SIP flood in attacker container..."
	@$(COMPOSE) exec -T attacker sh -lc "ps -eo pid,args | grep '[d]os-sipflood.py' | awk '{print \$$1}' | xargs -r kill -TERM || true"
	@echo "[+] DoS flood stopped (if it was running)."

dos-logs:
	@$(COMPOSE) exec -T attacker sh -lc "tail -n 40 /tmp/dos.log 2>/dev/null || echo 'No /tmp/dos.log yet'"

dos-check:
	@echo "[*] Monitoring FreeSWITCH memory for DoS impact..."
	@echo "[*] timeout=$(DOS_CHECK_TIMEOUT_SEC)s interval=$(DOS_CHECK_INTERVAL_SEC)s log=$(DOS_MEM_LOG)"
	@rm -f "$(DOS_MEM_LOG)"
	@i=0; \
	limit=$$(( $(DOS_CHECK_TIMEOUT_SEC) / $(DOS_CHECK_INTERVAL_SEC) )); \
	while [ $$i -le $$limit ]; do \
		TS=$$(date -u +"%Y-%m-%dT%H:%M:%SZ"); \
		CID="$$( $(COMPOSE) ps -q freeswitch )"; \
		STATUS=$$(docker inspect -f '{{.State.Status}}' $$CID 2>/dev/null || echo "not_found"); \
		MEM=$$(docker stats --no-stream --format '{{.MemUsage}}' $$CID 2>/dev/null || echo "n/a"); \
		echo "$$TS status=$$STATUS mem=$$MEM" | tee -a "$(DOS_MEM_LOG)"; \
		if [ "$$STATUS" != "running" ]; then \
			echo "[+] DoS success: freeswitch container status is '$$STATUS'."; \
			echo "[+] Memory timeline saved at $(DOS_MEM_LOG)"; \
			exit 0; \
		fi; \
		sleep $(DOS_CHECK_INTERVAL_SEC); \
		i=$$((i+1)); \
	done; \
	echo "[!] DoS check timed out: freeswitch did not crash within $(DOS_CHECK_TIMEOUT_SEC)s."; \
	echo "[i] Last samples:"; \
	tail -n 10 "$(DOS_MEM_LOG)" || true; \
	exit 1


auto-attack: stop build start
	@$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) \
		attacker_ip=$(ATTACKER_IP) victim_ip=$(TARGET_IP) \
		expected_sids=$(EXPECTED_SIDS) attack_type=$(ATTACK_TYPE) \
		probe_targets=$(ATTACKER_IP),$(TARGET_IP) probe_protocols=tcp,udp,icmp
	@echo "[*] Waiting for containers (3 seconds)..."
	@sleep 3
	@if [ "$(SCENARIO)" = "1" ]; then \
		$(MAKE) client-up SIP_SERVER="$(SIP_SERVER)" CLIENT_EXT="$(CLIENT_EXT)" CLIENT_PASS="$(CLIENT_PASS)"; \
		$(MAKE) client-wait-registered CLIENT_EXT="$(CLIENT_EXT)" CLIENT_WAIT_SEC="$(CLIENT_WAIT_SEC)"; \
			   $(RTC_EVENT) attack_start stack=$(STACK_ID) scenario=1 instance=$(INSTANCE) attack=sip_spoofing attacker_ip=$(ATTACKER_IP) victim_ip=$(TARGET_IP); \
		echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=1 instance=$(INSTANCE) attack=sip_spoofing"; \
		$(MAKE) spoof-attack TARGET_IP="$(TARGET_IP)" TARGET_EXT="$(TARGET_EXT)"; \
		sleep 2; \
		$(MAKE) client-check-spoof; \
		$(RTC_EVENT) attack_end stack=$(STACK_ID) scenario=1 instance=$(INSTANCE) attack=sip_spoofing; \
		echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=1 instance=$(INSTANCE) attack=sip_spoofing"; \
	elif [ "$(SCENARIO)" = "2" ]; then \
			   $(RTC_EVENT) attack_start stack=$(STACK_ID) scenario=2 instance=$(INSTANCE) attack=sip_flood attacker_ip=$(ATTACKER_IP) victim_ip=$(TARGET_IP); \
		echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=2 instance=$(INSTANCE) attack=sip_flood"; \
		$(MAKE) dos-start TARGET_IP="$(TARGET_IP)"; \
		$(MAKE) dos-check; \
		$(RTC_EVENT) attack_end stack=$(STACK_ID) scenario=2 instance=$(INSTANCE) attack=sip_flood; \
		echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=2 instance=$(INSTANCE) attack=sip_flood"; \
	else \
		echo "[!] Invalid SCENARIO=$(SCENARIO). Use 1 (spoofing) or 2 (dos)."; \
		exit 1; \
	fi
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)
	$(MAKE) stop

repeat-check:
	@echo "[*] Repetition test for scenario $(SCENARIO)"
	@echo "[*] runs=$(REPEAT_RUNS) min_success=$(REPEAT_MIN_SUCCESS) delay=$(REPEAT_DELAY_SEC)s"
	@echo "[*] log=$(REPEAT_LOG)"
	@rm -f "$(REPEAT_LOG)"
	@PASS=0; FAIL=0; i=1; \
	while [ $$i -le "$(REPEAT_RUNS)" ]; do \
		echo "========== RUN $$i/$(REPEAT_RUNS) ==========" | tee -a "$(REPEAT_LOG)"; \
		if $(MAKE) auto-attack \
			SCENARIO="$(SCENARIO)" \
			TARGET_IP="$(TARGET_IP)" \
			TARGET_EXT="$(TARGET_EXT)" \
			SIP_SERVER="$(SIP_SERVER)" \
			CLIENT_EXT="$(CLIENT_EXT)" \
			CLIENT_PASS="$(CLIENT_PASS)" \
			CLIENT_WAIT_SEC="$(CLIENT_WAIT_SEC)" \
			CLIENT_IP="$(CLIENT_IP)" \
			CLIENT_PORT="$(CLIENT_PORT)" \
			DOS_CHECK_TIMEOUT_SEC="$(DOS_CHECK_TIMEOUT_SEC)" \
			DOS_CHECK_INTERVAL_SEC="$(DOS_CHECK_INTERVAL_SEC)" \
			DOS_MEM_LOG="$(DOS_MEM_LOG)" \
			>> "$(REPEAT_LOG)" 2>&1; then \
			PASS=$$((PASS+1)); \
			echo "[RUN $$i] PASS ($$PASS pass / $$FAIL fail)" | tee -a "$(REPEAT_LOG)"; \
		else \
			FAIL=$$((FAIL+1)); \
			echo "[RUN $$i] FAIL ($$PASS pass / $$FAIL fail)" | tee -a "$(REPEAT_LOG)"; \
		fi; \
		if [ $$i -lt "$(REPEAT_RUNS)" ]; then \
			sleep "$(REPEAT_DELAY_SEC)"; \
		fi; \
		i=$$((i+1)); \
	done; \
	echo "========== SUMMARY ==========" | tee -a "$(REPEAT_LOG)"; \
	echo "scenario=$(SCENARIO) total=$(REPEAT_RUNS) pass=$$PASS fail=$$FAIL min_success=$(REPEAT_MIN_SUCCESS)" | tee -a "$(REPEAT_LOG)"; \
	if [ "$$PASS" -ge "$(REPEAT_MIN_SUCCESS)" ]; then \
		echo "[+] Condition satisfied."; \
		exit 0; \
	else \
		echo "[!] Condition NOT satisfied. Check $(REPEAT_LOG) for details."; \
		exit 1; \
	fi
