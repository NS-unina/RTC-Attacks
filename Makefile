DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := root
CHECK_AVAILABLE_TAG := RTC_CHECK_AVAILABLE
DRY_RUN_TAG := RTC_DRY_RUN

SERVICE ?=

run:
	@$(DOCKER_COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(DOCKER_COMPOSE) down --remove-orphans

stop-all-labs:
	cd public/labs && find . -maxdepth 2 -name Makefile -execdir make stop \;

build:
	# Previous implementation kept for traceability:
	# @$(DOCKER_COMPOSE) build --no-cache $(SERVICE)
	# Change rationale: default build now reuses Docker layer cache and BuildKit cache mounts.
	@DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 $(DOCKER_COMPOSE) build $(SERVICE)

build-no-cache:
	# Change rationale: keep an explicit full rebuild option when a clean build is required.
	@DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 $(DOCKER_COMPOSE) build --no-cache $(SERVICE)

is-available:
	@echo "$(CHECK_AVAILABLE_TAG)_BEGIN stack=$(STACK_ID)"
	@$(DOCKER_COMPOSE) config -q
	@SERVICES="$$( $(DOCKER_COMPOSE) config --services )"; \
	if [ -z "$$SERVICES" ]; then \
		echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) reason=no_services"; \
		exit 1; \
	fi; \
	for SVC in $$SERVICES; do \
		CID="$$( $(DOCKER_COMPOSE) ps -q $$SVC )"; \
		if [ -z "$$CID" ]; then \
			echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) service=$$SVC reason=not_running"; \
			exit 1; \
		fi; \
		STATE="$$(docker inspect -f '{{.State.Status}}' $$CID)"; \
		if [ "$$STATE" != "running" ]; then \
			echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) service=$$SVC reason=unexpected_state state=$$STATE"; \
			exit 1; \
		fi; \
		HEALTH="$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' $$CID)"; \
		if [ -n "$$HEALTH" ] && [ "$$HEALTH" != "healthy" ]; then \
			echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) service=$$SVC reason=unhealthy health=$$HEALTH"; \
			exit 1; \
		fi; \
		echo "$(CHECK_AVAILABLE_TAG)_OK stack=$(STACK_ID) service=$$SVC state=$$STATE"; \
	done; \
	echo "$(CHECK_AVAILABLE_TAG)_OK stack=$(STACK_ID) all_services=running"

dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@curl -fsS http://127.0.0.1:7681/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=ttyd_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=ttyd_http"
	@docker exec mongo mongosh --quiet -u root -p example --authenticationDatabase admin --eval "db.adminCommand({ ping: 1 }).ok" 2>/dev/null | grep -qx '1' || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=mongo_ping reason=not_ready"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=mongo_ping"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"


clean-captures:
	@echo "Cleaning up capture files..."
	@sudo rm -rf captures/*	

start-snort:
	@docker compose -f snort-compose.yaml up 