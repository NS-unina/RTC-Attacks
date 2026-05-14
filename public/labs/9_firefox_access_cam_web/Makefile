DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := 9_firefox_access_cam_web
CHECK_AVAILABLE_TAG := RTC_CHECK_AVAILABLE
DRY_RUN_TAG := RTC_DRY_RUN

SERVICE ?=

run:
	@$(DOCKER_COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(DOCKER_COMPOSE) down --remove-orphans

start-node:
	@docker exec -it node bash

build:
	@$(DOCKER_COMPOSE) build --no-cache $(SERVICE)
rebuild:
	@$(DOCKER_COMPOSE) down --rmi all --remove-orphans || true
	@$(DOCKER_COMPOSE) build --no-cache $(SERVICE)

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
		echo "$(CHECK_AVAILABLE_TAG)_OK stack=$(STACK_ID) service=$$SVC state=$$STATE"; \
	done; \
	echo "$(CHECK_AVAILABLE_TAG)_OK stack=$(STACK_ID) all_services=running"

dry-run:
	@echo "$(DRY_RUN_TAG)_BEGIN stack=$(STACK_ID)"
	@curl -fsS http://127.0.0.1/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=node_firefox_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=node_firefox_http"
	@curl -kfsS https://127.0.0.1:3333/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=gophish_admin reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=gophish_admin"
	@docker exec firefox sh -lc 'command -v firefox >/dev/null && test -n "$$DISPLAY" && test -d /tmp/.X11-unix' || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=firefox_gui_prereqs reason=missing_display_or_binary"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=firefox_gui_prereqs"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"
