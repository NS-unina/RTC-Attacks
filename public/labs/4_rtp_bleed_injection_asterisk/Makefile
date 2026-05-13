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
