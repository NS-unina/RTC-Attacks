SHARED_MK_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
RTC_EVENT := $(SHARED_MK_DIR)/ipc_send.py
CHECK_AVAILABLE_TAG := RTC_CHECK_AVAILABLE
INSTANCE ?= default
ATTACK_EVENT_SCENARIO ?= $(SCENARIO)
ATTACK_NAME ?= $(ATTACK_TYPE)



DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
ATTACK_WINDOW_TAG := RTC_ATTACK_WINDOW

COMPOSE_PROJECT_NAME ?= $(STACK_ID)$(if $(filter default,$(INSTANCE)),,_$(INSTANCE))
COMPOSE := COMPOSE_PROJECT_NAME=$(COMPOSE_PROJECT_NAME) $(DOCKER_COMPOSE)

SERVICE ?= 
INSTANCE_INDEX ?= $(if $(filter default,$(INSTANCE)),0,$(INSTANCE))

send_start_lab_event:
	@python $(RTC_EVENT) lab_ready stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE) \
		attacker_ip=$(ATTACKER_IP) victim_ip=$(TARGET_IP) \
		expected_sids=$(EXPECTED_SIDS) attack_type=$(ATTACK_TYPE) \
		probe_targets=$(ATTACKER_IP),$(TARGET_IP) probe_protocols=tcp,udp,icmp

send_start_attack_event:
	# Change rationale: make shared RTC attack event reusable across all labs/scenarios.
	@python $(RTC_EVENT) attack_start stack=$(STACK_ID) scenario=$(ATTACK_EVENT_SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_NAME) attacker_ip=$(ATTACKER_IP) victim_ip=$(TARGET_IP); \
		echo "$(ATTACK_WINDOW_TAG)_BEGIN ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(ATTACK_EVENT_SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_NAME)"; 

send_stop_attack_event:
	# Change rationale: keep attack window closing consistent with the dynamic start event.
	@python $(RTC_EVENT) attack_end stack=$(STACK_ID) scenario=$(ATTACK_EVENT_SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_NAME); \
			echo "$(ATTACK_WINDOW_TAG)_END ts_utc=$$(date -u +"%Y-%m-%dT%H:%M:%SZ") stack=$(STACK_ID) scenario=$(ATTACK_EVENT_SCENARIO) instance=$(INSTANCE) attack=$(ATTACK_NAME)"; 


send_stop_lab_event:
	@python $(RTC_EVENT) lab_stop stack=$(STACK_ID) scenario=$(SCENARIO) instance=$(INSTANCE)

ifndef DISABLE_SHARED_LIFECYCLE_TARGETS
stop:
	@$(COMPOSE) down --remove-orphans


print:
	@echo "SHARED_MK_DIR: $(SHARED_MK_DIR)"
	@echo "RTC_EVENT: $(RTC_EVENT)"

build:
	@$(COMPOSE) build $(SERVICE)

rebuild: 
	@$(COMPOSE) down --rmi all --remove-orphans || true
	@$(COMPOSE) build --no-cache $(SERVICE)

is-available:
	@echo "$(CHECK_AVAILABLE_TAG)_BEGIN stack=$(STACK_ID)"
	@$(COMPOSE) config -q
	@SERVICES="$$( $(COMPOSE) config --services )"; \
	if [ -z "$$SERVICES" ]; then \
		echo "$(CHECK_AVAILABLE_TAG)_FAIL stack=$(STACK_ID) reason=no_services"; \
		exit 1; \
	fi; \
	for SVC in $$SERVICES; do \
		CID="$$( $(COMPOSE) ps -q $$SVC )"; \
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
endif
