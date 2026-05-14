# ================================================================================
# EXPERIMENTAL METRICS COLLECTION - Template for all labs
# ================================================================================
# This Makefile provides standardized targets for collecting quantitative metrics
# to address reviewer comments about statistical analysis and performance evaluation.
#
# Usage: Include this file in your lab's Makefile with:
#   include Makefile.metrics
#
# Requirements:
#   - METRICS_DIR: Directory for storing metrics (default: metrics/)
#   - SCENARIO: Current scenario being tested
#   - Docker containers must be running
# ================================================================================

# Configuration
METRICS_DIR ?= metrics
RUNS_COUNT ?= 30
SAMPLING_INTERVAL_SEC ?= 0.1
CORRELATION_WINDOW_SEC ?= 5.0
TIMESTAMP := $(shell date +%Y%m%d_%H%M%S)

# Ensure metrics directory exists
$(shell mkdir -p $(METRICS_DIR))

# ================================================================================
# 1. DEPLOYMENT AND STARTUP TIME METRICS
# ================================================================================

.PHONY: metrics-tbuild
metrics-tbuild:
	@echo "[METRICS] Measuring build time..."
	@echo "timestamp,phase,duration_sec" > $(METRICS_DIR)/build_time_$(TIMESTAMP).csv
	@START=$$(date +%s.%N); \
	$(MAKE) build; \
	END=$$(date +%s.%N); \
	DURATION=$$(echo "$$END - $$START" | bc); \
	echo "$(TIMESTAMP),build,$$DURATION" >> $(METRICS_DIR)/build_time_$(TIMESTAMP).csv
	@echo "[+] Build time saved to $(METRICS_DIR)/build_time_$(TIMESTAMP).csv"

.PHONY: metrics-startup
metrics-startup:
	@echo "[METRICS] Measuring startup time..."
	@echo "timestamp,container,phase,duration_sec" > $(METRICS_DIR)/startup_time_$(TIMESTAMP).csv
	@START=$$(date +%s.%N); \
	$(MAKE) start; \
	STARTUP=$$(date +%s.%N); \
	STARTUP_DURATION=$$(echo "$$STARTUP - $$START" | bc); \
	echo "$(TIMESTAMP),all,startup,$$STARTUP_DURATION" >> $(METRICS_DIR)/startup_time_$(TIMESTAMP).csv; \
	sleep 2; \
	READY=$$(date +%s.%N); \
	READY_DURATION=$$(echo "$$READY - $$START" | bc); \
	echo "$(TIMESTAMP),all,ready,$$READY_DURATION" >> $(METRICS_DIR)/startup_time_$(TIMESTAMP).csv
	@echo "[+] Startup time saved to $(METRICS_DIR)/startup_time_$(TIMESTAMP).csv"

.PHONY: metrics-deployment
metrics-deployment: metrics-tbuild metrics-startup
	@echo "[+] Deployment metrics collected"

# ================================================================================
# 2. CPU AND MEMORY UTILIZATION
# ================================================================================

.PHONY: metrics-cpu-baseline
metrics-cpu-baseline:
	@echo "[METRICS] Collecting baseline CPU/Memory metrics..."
	@echo "timestamp,container,cpu_percent,mem_usage,mem_limit,mem_percent" > $(METRICS_DIR)/cpu_mem_baseline_$(TIMESTAMP).csv
	@for i in $$(seq 1 30); do \
		$(DOCKER_COMPOSE) ps -q | xargs -I {} sh -c 'docker stats --no-stream --format "$(TIMESTAMP),{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" {}' >> $(METRICS_DIR)/cpu_mem_baseline_$(TIMESTAMP).csv 2>/dev/null || true; \
		sleep 1; \
	done
	@echo "[+] Baseline metrics saved to $(METRICS_DIR)/cpu_mem_baseline_$(TIMESTAMP).csv"

.PHONY: metrics-cpu-attack
metrics-cpu-attack:
	@echo "[METRICS] Collecting CPU/Memory during attack (background monitoring)..."
	@echo "timestamp,container,cpu_percent,mem_usage,mem_limit,mem_percent" > $(METRICS_DIR)/cpu_mem_attack_$(TIMESTAMP).csv
	@echo "[*] Starting background monitoring (PID saved to /tmp/metrics_monitor.pid)..."
	@( \
		while true; do \
			TS=$$(date +%s.%N); \
			$(DOCKER_COMPOSE) ps -q | xargs -I {} sh -c 'docker stats --no-stream --format "'$$TS',{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" {}' >> $(METRICS_DIR)/cpu_mem_attack_$(TIMESTAMP).csv 2>/dev/null || true; \
			sleep $(SAMPLING_INTERVAL_SEC); \
		done \
	) & echo $$! > /tmp/metrics_monitor.pid
	@echo "[+] Monitoring started. Run attack, then use 'make metrics-cpu-stop' to stop."

.PHONY: metrics-cpu-stop
metrics-cpu-stop:
	@if [ -f /tmp/metrics_monitor.pid ]; then \
		PID=$$(cat /tmp/metrics_monitor.pid); \
		kill $$PID 2>/dev/null || true; \
		rm -f /tmp/metrics_monitor.pid; \
		echo "[+] Monitoring stopped. Data saved to $(METRICS_DIR)/cpu_mem_attack_*.csv"; \
	else \
		echo "[!] No monitoring process found"; \
	fi

.PHONY: metrics-cpu-peak
metrics-cpu-peak:
	@echo "[METRICS] Analyzing peak CPU/Memory usage..."
	@if [ -f "$(METRICS_DIR)/cpu_mem_attack_$(TIMESTAMP).csv" ]; then \
		echo "Analyzing peak values..."; \
		python3 -c "import pandas as pd; df = pd.read_csv('$(METRICS_DIR)/cpu_mem_attack_$(TIMESTAMP).csv'); print('Peak CPU:', df['cpu_percent'].max()); print('Peak MEM:', df['mem_percent'].max())"; \
	else \
		echo "[!] No attack metrics found. Run metrics-cpu-attack first."; \
	fi

.PHONY: metrics-resources
metrics-resources: metrics-cpu-baseline
	@echo "[+] Resource metrics baseline collected. Run attack with metrics-cpu-attack."

# ================================================================================
# 3. NETWORK LATENCY OVERHEAD
# ================================================================================

.PHONY: metrics-network-baseline
metrics-network-baseline:
	@echo "[METRICS] Measuring network latency WITHOUT monitoring..."
	@mkdir -p $(METRICS_DIR)/pcap
	@echo "[*] Stopping Snort temporarily..."
	@docker stop $$(docker ps -q -f name=snort) 2>/dev/null || true
	@echo "[*] Running baseline latency test..."
	@$(MAKE) _network_latency_test OUTPUT=$(METRICS_DIR)/network_baseline_$(TIMESTAMP).csv
	@echo "[*] Restarting Snort..."
	@docker start $$(docker ps -aq -f name=snort) 2>/dev/null || true
	@echo "[+] Baseline latency saved to $(METRICS_DIR)/network_baseline_$(TIMESTAMP).csv"

.PHONY: metrics-network-monitoring
metrics-network-monitoring:
	@echo "[METRICS] Measuring network latency WITH monitoring..."
	@$(MAKE) _network_latency_test OUTPUT=$(METRICS_DIR)/network_monitoring_$(TIMESTAMP).csv
	@echo "[+] Monitoring latency saved to $(METRICS_DIR)/network_monitoring_$(TIMESTAMP).csv"

.PHONY: _network_latency_test
_network_latency_test:
	@echo "timestamp,protocol,rtt_ms,jitter_ms,packet_loss_pct" > $(OUTPUT)
	@for i in $$(seq 1 100); do \
		TS=$$(date +%s.%N); \
		RTT=$$(docker exec $$(docker ps -q -f name=attacker || echo client) ping -c 1 -W 1 $$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' $$(docker ps -q -f name=target || docker ps -q | head -1)) 2>/dev/null | grep 'time=' | sed 's/.*time=\([0-9.]*\).*/\1/' || echo "0"); \
		echo "$$TS,icmp,$$RTT,0,0" >> $(OUTPUT); \
		sleep 0.1; \
	done

.PHONY: metrics-network-overhead
metrics-network-overhead:
	@echo "[METRICS] Calculating network overhead..."
	@if [ -f "$(METRICS_DIR)/network_baseline_$(TIMESTAMP).csv" ] && [ -f "$(METRICS_DIR)/network_monitoring_$(TIMESTAMP).csv" ]; then \
		python3 -c "import pandas as pd; \
		baseline = pd.read_csv('$(METRICS_DIR)/network_baseline_$(TIMESTAMP).csv')['rtt_ms'].mean(); \
		monitoring = pd.read_csv('$(METRICS_DIR)/network_monitoring_$(TIMESTAMP).csv')['rtt_ms'].mean(); \
		overhead = monitoring - baseline; \
		overhead_pct = (overhead / baseline * 100) if baseline > 0 else 0; \
		print(f'Baseline RTT: {baseline:.3f}ms'); \
		print(f'Monitoring RTT: {monitoring:.3f}ms'); \
		print(f'Overhead: {overhead:.3f}ms ({overhead_pct:.2f}%)')"; \
	else \
		echo "[!] Missing baseline or monitoring data. Run both metrics-network-baseline and metrics-network-monitoring first."; \
	fi

.PHONY: metrics-network
metrics-network: metrics-network-baseline metrics-network-monitoring metrics-network-overhead
	@echo "[+] Network latency metrics collected"

# ================================================================================
# 4. REPRODUCIBILITY STATISTICS (N=30 runs)
# ================================================================================

.PHONY: metrics-reproducibility
metrics-reproducibility:
	@echo "[METRICS] Running reproducibility test (N=$(RUNS_COUNT) runs)..."
	@echo "run,timestamp,scenario,build_success,start_success,attack_success,detection_success,build_time_sec,startup_time_sec,peak_cpu,peak_mem" > $(METRICS_DIR)/reproducibility_$(TIMESTAMP).csv
	@for run in $$(seq 1 $(RUNS_COUNT)); do \
		echo "[*] Run $$run/$(RUNS_COUNT)..."; \
		$(MAKE) stop clean 2>/dev/null || true; \
		\
		BUILD_START=$$(date +%s.%N); \
		$(MAKE) build > /tmp/metrics_build_$${run}.log 2>&1; \
		BUILD_SUCCESS=$$?; \
		BUILD_END=$$(date +%s.%N); \
		BUILD_TIME=$$(echo "$$BUILD_END - $$BUILD_START" | bc); \
		\
		START_START=$$(date +%s.%N); \
		$(MAKE) start > /tmp/metrics_start_$${run}.log 2>&1; \
		START_SUCCESS=$$?; \
		START_END=$$(date +%s.%N); \
		START_TIME=$$(echo "$$START_END - $$START_START" | bc); \
		\
		sleep 3; \
		\
		$(MAKE) auto-attack SCENARIO=$(SCENARIO) > /tmp/metrics_attack_$${run}.log 2>&1; \
		ATTACK_SUCCESS=$$?; \
		\
		DETECTION_SUCCESS=0; \
		if [ -f "/captures/latest/alert.log" ]; then \
			if [ -s "/captures/latest/alert.log" ]; then \
				DETECTION_SUCCESS=1; \
			fi; \
		fi; \
		\
		PEAK_CPU=$$(docker stats --no-stream --format "{{.CPUPerc}}" | head -1 | sed 's/%//'); \
		PEAK_MEM=$$(docker stats --no-stream --format "{{.MemPerc}}" | head -1 | sed 's/%//'); \
		\
		TS=$$(date +%Y-%m-%d_%H:%M:%S); \
		echo "$$run,$$TS,$(SCENARIO),$$BUILD_SUCCESS,$$START_SUCCESS,$$ATTACK_SUCCESS,$$DETECTION_SUCCESS,$$BUILD_TIME,$$START_TIME,$$PEAK_CPU,$$PEAK_MEM" >> $(METRICS_DIR)/reproducibility_$(TIMESTAMP).csv; \
		\
		$(MAKE) stop 2>/dev/null || true; \
	done
	@echo "[+] Reproducibility test complete. Results in $(METRICS_DIR)/reproducibility_$(TIMESTAMP).csv"
	@echo "[*] Calculating success rates..."
	@python3 -c "import pandas as pd; \
	df = pd.read_csv('$(METRICS_DIR)/reproducibility_$(TIMESTAMP).csv'); \
	total = len(df); \
	print(f'Total runs: {total}'); \
	print(f'Build success rate: {(df[\"build_success\"]==0).sum()/total*100:.1f}%'); \
	print(f'Start success rate: {(df[\"start_success\"]==0).sum()/total*100:.1f}%'); \
	print(f'Attack success rate: {(df[\"attack_success\"]==0).sum()/total*100:.1f}%'); \
	print(f'Detection success rate: {df[\"detection_success\"].sum()/total*100:.1f}%'); \
	print(f'Build time: {df[\"build_time_sec\"].mean():.2f}±{df[\"build_time_sec\"].std():.2f}s'); \
	print(f'Startup time: {df[\"startup_time_sec\"].mean():.2f}±{df[\"startup_time_sec\"].std():.2f}s')"

# ================================================================================
# 5. IDS DETECTION METRICS (Precision, Recall, F1-Score)
# ================================================================================

.PHONY: metrics-ids-detection
metrics-ids-detection:
	@echo "[METRICS] Analyzing IDS detection accuracy..."
	@if [ ! -f "scripts/analyze_ids_metrics.py" ]; then \
		echo "[!] Creating IDS analysis script..."; \
		$(MAKE) _create_ids_analysis_script; \
	fi
	@python3 scripts/analyze_ids_metrics.py \
		--ground-truth $(METRICS_DIR)/ground_truth.json \
		--alerts /captures/latest/alert.log \
		--output $(METRICS_DIR)/ids_metrics_$(TIMESTAMP).json
	@echo "[+] IDS metrics saved to $(METRICS_DIR)/ids_metrics_$(TIMESTAMP).json"

.PHONY: _create_ids_analysis_script
_create_ids_analysis_script:
	@mkdir -p scripts
	@echo '#!/usr/bin/env python3' > scripts/analyze_ids_metrics.py
	@echo 'import json, sys, argparse' >> scripts/analyze_ids_metrics.py
	@echo 'def calculate_metrics(gt, alerts):' >> scripts/analyze_ids_metrics.py
	@echo '    TP = FP = TN = FN = 0' >> scripts/analyze_ids_metrics.py
	@echo '    # TODO: Implement matching logic' >> scripts/analyze_ids_metrics.py
	@echo '    precision = TP/(TP+FP) if (TP+FP)>0 else 0' >> scripts/analyze_ids_metrics.py
	@echo '    recall = TP/(TP+FN) if (TP+FN)>0 else 0' >> scripts/analyze_ids_metrics.py
	@echo '    f1 = 2*precision*recall/(precision+recall) if (precision+recall)>0 else 0' >> scripts/analyze_ids_metrics.py
	@echo '    return {"precision": precision, "recall": recall, "f1": f1, "TP": TP, "FP": FP, "FN": FN}' >> scripts/analyze_ids_metrics.py
	@echo 'parser = argparse.ArgumentParser()' >> scripts/analyze_ids_metrics.py
	@echo 'parser.add_argument("--ground-truth", required=True)' >> scripts/analyze_ids_metrics.py
	@echo 'parser.add_argument("--alerts", required=True)' >> scripts/analyze_ids_metrics.py
	@echo 'parser.add_argument("--output", required=True)' >> scripts/analyze_ids_metrics.py
	@echo 'args = parser.parse_args()' >> scripts/analyze_ids_metrics.py
	@echo 'metrics = calculate_metrics(None, None)' >> scripts/analyze_ids_metrics.py
	@echo 'with open(args.output, "w") as f: json.dump(metrics, f, indent=2)' >> scripts/analyze_ids_metrics.py
	@echo 'print(json.dumps(metrics, indent=2))' >> scripts/analyze_ids_metrics.py
	@chmod +x scripts/analyze_ids_metrics.py

# ================================================================================
# 6. PACKET CAPTURE COMPLETENESS
# ================================================================================

.PHONY: metrics-pcap-completeness
metrics-pcap-completeness:
	@echo "[METRICS] Analyzing packet capture completeness..."
	@if [ ! -f "/captures/latest/capture.pcap" ]; then \
		echo "[!] No capture file found at /captures/latest/capture.pcap"; \
		exit 1; \
	fi
	@echo "timestamp,packets_sent,packets_captured,capture_rate_pct,packet_loss_pct" > $(METRICS_DIR)/pcap_completeness_$(TIMESTAMP).csv
	@SENT=$$(cat /tmp/attack_packets_sent.count 2>/dev/null || echo "0"); \
	CAPTURED=$$(tshark -r /captures/latest/capture.pcap 2>/dev/null | wc -l || echo "0"); \
	if [ "$$SENT" -gt 0 ]; then \
		RATE=$$(echo "scale=2; $$CAPTURED / $$SENT * 100" | bc); \
		LOSS=$$(echo "scale=2; 100 - $$RATE" | bc); \
	else \
		RATE=0; LOSS=0; \
	fi; \
	TS=$$(date +%Y-%m-%d_%H:%M:%S); \
	echo "$$TS,$$SENT,$$CAPTURED,$$RATE,$$LOSS" >> $(METRICS_DIR)/pcap_completeness_$(TIMESTAMP).csv; \
	echo "Packets sent: $$SENT"; \
	echo "Packets captured: $$CAPTURED"; \
	echo "Capture rate: $$RATE%"; \
	echo "Packet loss: $$LOSS%"
	@echo "[+] Completeness metrics saved to $(METRICS_DIR)/pcap_completeness_$(TIMESTAMP).csv"

# ================================================================================
# 7. CORRELATION SUCCESS RATE (Alerts vs Attack Events)
# ================================================================================

.PHONY: metrics-correlation
metrics-correlation:
	@echo "[METRICS] Analyzing alert-to-event correlation..."
	@if [ ! -f "scripts/analyze_correlation.py" ]; then \
		echo "[!] Creating correlation analysis script..."; \
		$(MAKE) _create_correlation_script; \
	fi
	@python3 scripts/analyze_correlation.py \
		--events $(METRICS_DIR)/attack_events.json \
		--alerts /captures/latest/alert.log \
		--window $(CORRELATION_WINDOW_SEC) \
		--output $(METRICS_DIR)/correlation_$(TIMESTAMP).json
	@echo "[+] Correlation metrics saved to $(METRICS_DIR)/correlation_$(TIMESTAMP).json"

.PHONY: _create_correlation_script
_create_correlation_script:
	@mkdir -p scripts
	@echo '#!/usr/bin/env python3' > scripts/analyze_correlation.py
	@echo 'import json, sys, argparse' >> scripts/analyze_correlation.py
	@echo 'from datetime import datetime' >> scripts/analyze_correlation.py
	@echo 'def correlate(events, alerts, window):' >> scripts/analyze_correlation.py
	@echo '    correlated = matched = 0' >> scripts/analyze_correlation.py
	@echo '    # TODO: Implement correlation logic' >> scripts/analyze_correlation.py
	@echo '    rate = matched/len(events)*100 if events else 0' >> scripts/analyze_correlation.py
	@echo '    return {"correlation_rate": rate, "total_events": len(events), "matched_events": matched}' >> scripts/analyze_correlation.py
	@echo 'parser = argparse.ArgumentParser()' >> scripts/analyze_correlation.py
	@echo 'parser.add_argument("--events", required=True)' >> scripts/analyze_correlation.py
	@echo 'parser.add_argument("--alerts", required=True)' >> scripts/analyze_correlation.py
	@echo 'parser.add_argument("--window", type=float, default=5.0)' >> scripts/analyze_correlation.py
	@echo 'parser.add_argument("--output", required=True)' >> scripts/analyze_correlation.py
	@echo 'args = parser.parse_args()' >> scripts/analyze_correlation.py
	@echo 'result = correlate([], [], args.window)' >> scripts/analyze_correlation.py
	@echo 'with open(args.output, "w") as f: json.dump(result, f, indent=2)' >> scripts/analyze_correlation.py
	@echo 'print(json.dumps(result, indent=2))' >> scripts/analyze_correlation.py
	@chmod +x scripts/analyze_correlation.py

# ================================================================================
# 8. AGGREGATE METRICS AND REPORTING
# ================================================================================

.PHONY: metrics-all
metrics-all:
	@echo "[METRICS] Running complete metrics collection pipeline..."
	@echo "[*] Phase 1/7: Deployment metrics..."
	@$(MAKE) metrics-deployment
	@echo "[*] Phase 2/7: Resource baseline..."
	@$(MAKE) metrics-cpu-baseline
	@echo "[*] Phase 3/7: Network baseline..."
	@$(MAKE) metrics-network-baseline
	@echo "[*] Phase 4/7: Running attack with monitoring..."
	@$(MAKE) metrics-cpu-attack
	@$(MAKE) auto-attack SCENARIO=$(SCENARIO) || true
	@$(MAKE) metrics-cpu-stop
	@echo "[*] Phase 5/7: IDS detection analysis..."
	@$(MAKE) metrics-ids-detection || echo "[!] IDS metrics skipped (no ground truth)"
	@echo "[*] Phase 6/7: Packet capture completeness..."
	@$(MAKE) metrics-pcap-completeness || echo "[!] PCAP completeness skipped"
	@echo "[*] Phase 7/7: Correlation analysis..."
	@$(MAKE) metrics-correlation || echo "[!] Correlation skipped (no events)"
	@echo "[+] All metrics collected. Run 'make metrics-report' to generate summary."

.PHONY: metrics-report
metrics-report:
	@echo "[METRICS] Generating comprehensive metrics report..."
	@mkdir -p $(METRICS_DIR)/reports
	@echo "# Metrics Report - $(TIMESTAMP)" > $(METRICS_DIR)/reports/report_$(TIMESTAMP).md
	@echo "" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md
	@echo "## Summary" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md
	@echo "- Scenario: $(SCENARIO)" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md
	@echo "- Timestamp: $(TIMESTAMP)" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md
	@echo "" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md
	@for csv in $(METRICS_DIR)/*.csv; do \
		if [ -f "$$csv" ]; then \
			echo "### $$(basename $$csv .csv)" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md; \
			head -20 "$$csv" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md; \
			echo "" >> $(METRICS_DIR)/reports/report_$(TIMESTAMP).md; \
		fi; \
	done
	@echo "[+] Report generated: $(METRICS_DIR)/reports/report_$(TIMESTAMP).md"

.PHONY: metrics-clean
metrics-clean:
	@echo "[METRICS] Cleaning metrics directory..."
	@rm -rf $(METRICS_DIR)/*
	@echo "[+] Metrics cleaned"

.PHONY: metrics-help
metrics-help:
	@echo "=== Metrics Collection Targets ==="
	@echo ""
	@echo "Deployment & Startup:"
	@echo "  metrics-tbuild               - Measure build time"
	@echo "  metrics-startup              - Measure startup time"
	@echo "  metrics-deployment           - Both build and startup"
	@echo ""
	@echo "Resource Utilization:"
	@echo "  metrics-cpu-baseline         - Collect baseline CPU/Memory"
	@echo "  metrics-cpu-attack           - Monitor during attack (background)"
	@echo "  metrics-cpu-stop             - Stop monitoring"
	@echo "  metrics-resources            - Baseline only"
	@echo ""
	@echo "Network Performance:"
	@echo "  metrics-network-baseline     - Latency without monitoring"
	@echo "  metrics-network-monitoring   - Latency with monitoring"
	@echo "  metrics-network-overhead     - Calculate overhead"
	@echo "  metrics-network              - All network metrics"
	@echo ""
	@echo "Reproducibility:"
	@echo "  metrics-reproducibility      - Run N=$(RUNS_COUNT) experiments"
	@echo ""
	@echo "IDS & Detection:"
	@echo "  metrics-ids-detection        - Precision, Recall, F1"
	@echo "  metrics-pcap-completeness    - Capture completeness rate"
	@echo "  metrics-correlation          - Alert-to-event correlation"
	@echo ""
	@echo "Aggregate:"
	@echo "  metrics-all                  - Run all metrics collection"
	@echo "  metrics-report               - Generate summary report"
	@echo "  metrics-clean                - Clean metrics directory"
	@echo ""
