DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := 7_8_vdo_ninja_xss_nosqli
CHECK_AVAILABLE_TAG := RTC_CHECK_AVAILABLE
DRY_RUN_TAG := RTC_DRY_RUN

SERVICE ?=

run:
	@$(DOCKER_COMPOSE) up -d --remove-orphans

start: run

stop:
	@$(DOCKER_COMPOSE) down --remove-orphans

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
	@curl -fsS http://127.0.0.1:9000/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=mongoose_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=mongoose_http"
	@STATUS_CODE="$$(curl -s -o /tmp/vdo-nosqli-dry-run.out -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{\"username\":\"dry-run\",\"password\":\"dry-run\"}' http://127.0.0.1:9000/login)"; \
	if [ "$$STATUS_CODE" != "200" ] && [ "$$STATUS_CODE" != "404" ]; then \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=mongoose_login_endpoint reason=unexpected_status status=$$STATUS_CODE"; \
		exit 1; \
	fi; \
	echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=mongoose_login_endpoint status=$$STATUS_CODE"
	@curl -fsS http://127.0.0.1/ >/dev/null || { \
		echo "$(DRY_RUN_TAG)_FAIL stack=$(STACK_ID) check=vdoninja_http reason=unreachable"; \
		exit 1; \
	}
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) check=vdoninja_http"
	@echo "$(DRY_RUN_TAG)_OK stack=$(STACK_ID) ready=true"
