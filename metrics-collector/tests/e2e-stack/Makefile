COMPOSE := docker compose

.PHONY: rebuild
rebuild:
	$(COMPOSE) build

.PHONY: run
run:
	$(COMPOSE) up -d

.PHONY: is-available
is-available:
	# Previous implementation (kept for traceability):
	# @$(COMPOSE) ps --status running | grep -q attacker
	# @$(COMPOSE) ps --status running | grep -q target
	#
	# Updated implementation:
	# Ensure all realistic e2e services are up before probes start.
	@$(COMPOSE) ps --status running | grep -q attacker
	@$(COMPOSE) ps --status running | grep -q httpd_frontend
	@$(COMPOSE) ps --status running | grep -q httpd_backend
	@$(COMPOSE) ps --status running | grep -q dns_resolver

.PHONY: dry-run
dry-run:
	# Previous implementation (kept for traceability):
	# $(COMPOSE) exec -T attacker sh -lc 'echo dry-run-ok'
	#
	# Updated implementation:
	# Validate real service reachability from the attacker container.
	$(COMPOSE) exec -T attacker sh -lc '\
		wget -qO- http://httpd_frontend/ >/dev/null && \
		wget -qO- http://httpd_backend/ >/dev/null && \
		nslookup example.org dns_resolver >/dev/null 2>&1 && \
		echo dry-run-ok'

.PHONY: auto-attack
auto-attack:
	# Previous implementation (kept for traceability):
	# $(COMPOSE) exec -T attacker sh -lc '\
	# 	i=0; \
	# 	while [ $$i -lt 15 ]; do \
	# 		head -c 1048576 /dev/zero > /tmp/load_$$i.bin; \
	# 		sha256sum /tmp/load_$$i.bin >/dev/null; \
	# 		rm -f /tmp/load_$$i.bin; \
	# 		ping -c 1 target >/dev/null 2>&1 || true; \
	# 		i=$$((i + 1)); \
	# 	done'
	#
	# Updated implementation:
	# Keep resource load generation and add realistic HTTP/DNS traffic.
	$(COMPOSE) exec -T attacker sh -lc '\
		i=0; \
		while [ $$i -lt 15 ]; do \
			head -c 1048576 /dev/zero > /tmp/load_$$i.bin; \
			sha256sum /tmp/load_$$i.bin >/dev/null; \
			rm -f /tmp/load_$$i.bin; \
			ping -c 1 httpd_frontend >/dev/null 2>&1 || true; \
			ping -c 1 httpd_backend >/dev/null 2>&1 || true; \
			ping -c 1 dns_resolver >/dev/null 2>&1 || true; \
			wget -qO- http://httpd_frontend/ >/dev/null 2>&1 || true; \
			wget -qO- http://httpd_backend/ >/dev/null 2>&1 || true; \
			nslookup example.org dns_resolver >/dev/null 2>&1 || true; \
			i=$$((i + 1)); \
		done'

.PHONY: stop
stop:
	$(COMPOSE) down -v --remove-orphans
