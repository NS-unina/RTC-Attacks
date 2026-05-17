DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")
STACK_ID := root
DRY_RUN_TAG := RTC_DRY_RUN

# Python interpreter for experiments: use project venv if present, else system python3
PYTHON := $(shell [ -f .venv/bin/python3 ] && echo .venv/bin/python3 || echo python3)

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

clean-analysis:
	@echo "Cleaning up analysis files..."
	@rm -rf analysis/*

clean-experiment-results:
	@echo "Cleaning up experiment result files..."
	@rm -rf experiments/results/*
	@rm -rf results/*


cleanup-all:
	@echo "Stopping all lab scenarios..."
	@$(MAKE) stop-all-labs || true
	@echo "Removing stopped containers..."
	@docker container prune -f
	@echo "Removing unused networks..."
	@docker network prune -f
	@echo "Cleaning captures..."
	@$(MAKE) clean-captures
	@echo "Cleaning analysis..."
	@$(MAKE) clean-analysis
	@echo "Cleaning experiment results..."
	@$(MAKE) clean-experiment-results
	@echo "Cleanup complete. Ready for isolated scenario test."

start-suricata:
	# Change rationale: Suricata is the single supported IDS runtime for experiment workflow.
	@docker compose -f suricata-compose.yaml up -d

stop-suricata:
	@docker compose -f suricata-compose.yaml down --remove-orphans

suricata-use-baseline:
	@echo "Switching to baseline rules (v1, before fine-tuning)..."
	@cp suricata/local.rules.v1-baseline suricata/local.rules
	@echo "Baseline rules activated. Restart Suricata to apply: make stop-suricata && make start-suricata"

suricata-restore-tuned:
	@echo "Restoring tuned rules from git..."
	@git restore suricata/local.rules || echo "Warning: git restore failed, keeping current version"
	@echo "Tuned rules restored. Restart Suricata to apply: make stop-suricata && make start-suricata"

suricata-diff-rules:
	@echo "=== Comparing baseline vs tuned rules ==="
	@diff -u suricata/local.rules.v1-baseline suricata/local.rules || true

sync-timezone:
	@echo "Synchronizing timezone across all Docker Compose files..."
	@python3 scripts/sync_timezone_compose.py --repo-root $(CURDIR)
	@echo "Timezone sync applied to all scenario docker-compose.yaml files"
	@echo "NOTE: suricata-compose.yaml is already configured with timezone mount"
	@echo "Restart containers to apply: make cleanup-all && make start-suricata"

ids-build-attack-events:
	@if [ -z "$(RUNNER_SUMMARY)" ]; then echo "RUNNER_SUMMARY is required"; exit 1; fi
	@$(PYTHON) experiments/pipeline/ids_dataset_pipeline.py build-attack-events \
		--runner-summary "$(RUNNER_SUMMARY)" \
		--output "$(or $(ATTACK_EVENTS_OUT),experiments/results/ids_pipeline/attack_events.json)"

ids-build-alerts:
	@$(PYTHON) experiments/pipeline/ids_dataset_pipeline.py build-alerts \
		--pcap-input "$(or $(PCAP_INPUT),captures/latest/pcap)" \
		--output "$(or $(ALERTS_OUTPUT),experiments/results/ids_pipeline/alerts.jsonl)" \
		--project-root "$(CURDIR)"

ids-build-dataset:
	@if [ -z "$(ATTACK_EVENTS)" ]; then echo "ATTACK_EVENTS is required"; exit 1; fi
	@$(PYTHON) experiments/pipeline/ids_dataset_pipeline.py build-dataset \
		--pcap-input "$(or $(PCAP_INPUT),captures/latest/pcap)" \
		--alerts "$(or $(ALERTS_INPUT),experiments/results/ids_pipeline/alerts.jsonl)" \
		--attack-events "$(ATTACK_EVENTS)" \
		--out-csv "$(or $(IDS_DATASET_CSV),experiments/results/ids_pipeline/ids_dataset.csv)" \
		--out-parquet "$(or $(IDS_DATASET_PARQUET),experiments/results/ids_pipeline/ids_dataset.parquet)" \
		--metrics-out "$(or $(DETECTION_METRICS_OUT),experiments/results/ids_pipeline/detection_metrics.json)" \
		--match-window-sec "$(or $(MATCH_WINDOW_SEC),3)"

ids-validate-alerts:
	@if [ -z "$(RUNNER_SUMMARY)" ]; then echo "RUNNER_SUMMARY is required"; exit 1; fi
	@$(PYTHON) experiments/pipeline/ids_dataset_pipeline.py validate-alerts \
		--alerts "$(or $(ALERTS_INPUT),experiments/results/ids_pipeline/alerts.jsonl)" \
		--runner-summary "$(RUNNER_SUMMARY)" \
		--output "$(or $(ALERT_VALIDATION_OUT),experiments/results/ids_pipeline/alert_validation.json)" \
		--window-pre-sec "$(or $(ALERT_WINDOW_PRE_SEC),0)" \
		--window-post-sec "$(or $(ALERT_WINDOW_POST_SEC),5)" \
		--timeline-bin-sec "$(or $(TIMELINE_BIN_SEC),1)"

ids-validate-alerts-strict:
	@$(MAKE) ids-validate-alerts \
		RUNNER_SUMMARY="$(RUNNER_SUMMARY)" \
		ALERTS_INPUT="$(ALERTS_INPUT)" \
		ALERT_VALIDATION_OUT="$(or $(ALERT_VALIDATION_OUT),experiments/results/ids_pipeline/alert_validation_strict.json)" \
		ALERT_WINDOW_PRE_SEC="$(ALERT_WINDOW_PRE_SEC)" \
		ALERT_WINDOW_POST_SEC="$(ALERT_WINDOW_POST_SEC)" \
		TIMELINE_BIN_SEC="$(TIMELINE_BIN_SEC)"

# --- Experiments ---

exp1-baseline:
	@$(PYTHON) -m experiments.exp1_baseline.runner \
		--scenarios "$(or $(SCENARIOS),1,2,3,4,5,6,7,8,9)" \
		--repetitions "$(or $(REPETITIONS),30)" \
		--monitoring "$(or $(MONITORING),on)" \
		$(if $(OUTPUT_DIR),--output-dir "$(OUTPUT_DIR)",)

exp2-scalability:
	@$(PYTHON) -m experiments.exp2_scalability.runner \
		--n-users-steps "$(or $(N_USERS_STEPS),1,5,10,20)" \
		--scenario "$(or $(SCENARIO),4)" \
		--monitoring "$(or $(MONITORING),on)" \
		--interval-sec "$(or $(INTERVAL_SEC),45)" \
		$(if $(OUTPUT_DIR),--output-dir "$(OUTPUT_DIR)",)

exp3-robustness:
	@$(PYTHON) -m experiments.exp3_robustness.runner \
		--load-levels "$(or $(LOAD_LEVELS),0,2,4,6,8)" \
		--probe-scenario "$(or $(PROBE_SCENARIO),7)" \
		--background-scenario "$(or $(BACKGROUND_SCENARIO),4)" \
		$(if $(OUTPUT_DIR),--output-dir "$(OUTPUT_DIR)",)

experiments-help:
	@echo "Active experiment workflow:"
	@echo "  make exp1-baseline REPETITIONS=30 MONITORING=on"
	@echo "  make exp2-scalability N_USERS_STEPS=1,5,10,20 SCENARIO=4 MONITORING=on"
	@echo "  make exp3-robustness LOAD_LEVELS=0,2,4,6,8 PROBE_SCENARIO=7 BACKGROUND_SCENARIO=4"
	@echo "  make stop-suricata  # only if a run is interrupted"
	@echo "Outputs: experiments/results/"
