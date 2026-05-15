DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
NUCLEI_POC :=/root/nuclei-templates/http/cves/2025/CVE-2025-62613.yaml

SERVICE ?=
IP_ADDRESS ?= 192.168.1.50

start:
	@$(DOCKER_COMPOSE) up -d

stop:
	@$(DOCKER_COMPOSE) down

build:
	@$(DOCKER_COMPOSE) build $(SERVICE)

build-nuclei:
	@docker build -t poc-7vdoninja ./nuclei

run-nuclei: build-nuclei
	@docker run --rm -it --net=host --name poc-7 poc-7vdoninja -t ${NUCLEI_POC} -u http://${IP_ADDRESS}
	@echo "[*] XSS Detected"