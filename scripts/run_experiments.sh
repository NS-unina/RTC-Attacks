#!/usr/bin/env bash
#
# Automated Experimental Runner for RTC-Attacks Testbed
# Esegue N run di ogni scenario e raccoglie tutte le metriche
#
# Usage: ./run_experiments.sh [num_runs] [scenario]
#        ./run_experiments.sh 30              # Tutti gli scenari, 30 run ciascuno
#        ./run_experiments.sh 5 4_rtp_bleed   # Solo scenario specifico, 5 run

set -euo pipefail

# Configurazione
NUM_RUNS=${1:-30}
SPECIFIC_SCENARIO=${2:-""}
OUTPUT_DIR="experimental_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="$OUTPUT_DIR/run_$TIMESTAMP"

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="$RUN_DIR/experiment.log"

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"
}

# Inizializzazione
init_experiment() {
    log "Initializing experimental run..."
    mkdir -p "$RUN_DIR"/{metrics,logs,captures,analysis}
    
    # Save configuration
    cat > "$RUN_DIR/config.json" <<EOF
{
    "num_runs": $NUM_RUNS,
    "timestamp": "$TIMESTAMP",
    "scenarios": $(get_scenarios_json),
    "hostname": "$(hostname)",
    "kernel": "$(uname -r)",
    "docker_version": "$(docker --version | cut -d' ' -f3)"
}
EOF
    
    log "Output directory: $RUN_DIR"
}

# Lista scenari da testare
get_scenarios() {
    if [ -n "$SPECIFIC_SCENARIO" ]; then
        echo "$SPECIFIC_SCENARIO"
    else
        # Tutti gli scenari in public/labs/
        find public/labs -maxdepth 1 -type d ! -name "labs" -printf "%f\n" | sort
    fi
}

get_scenarios_json() {
    scenarios=$(get_scenarios)
    echo -n "["
    first=true
    for scenario in $scenarios; do
        if [ "$first" = true ]; then
            first=false
        else
            echo -n ","
        fi
        echo -n "\"$scenario\""
    done
    echo "]"
}

# Cleanup ambiente tra run
cleanup_environment() {
    log "Cleaning up environment..."
    
    # Stop tutti i container
    docker-compose down -v 2>/dev/null || true
    
    # Kill processi rimasti
    pkill -f "docker-compose" || true
    
    # Pulizia vecchie catture
    rm -rf captures/* || true
    
    # Attesa per assicurare pulizia completa
    sleep 2
    
    log "Environment cleaned"
}

# Misurazione deployment timing
measure_deployment_timing() {
    local scenario=$1
    local run_number=$2
    local output_file="$RUN_DIR/metrics/${scenario}_run${run_number}_timing.json"
    
    log "Measuring deployment timing for $scenario (run $run_number)..."
    
    local start_total=$(date +%s.%N)
    
    # Build time
    local start_build=$(date +%s.%N)
    cd "public/labs/$scenario"
    make build >> "$RUN_DIR/logs/${scenario}_run${run_number}_build.log" 2>&1
    local build_success=$?
    local end_build=$(date +%s.%N)
    local build_time=$(echo "$end_build - $start_build" | bc)
    cd - > /dev/null
    
    # Startup time
    local start_startup=$(date +%s.%N)
    cd "public/labs/$scenario"
    make start >> "$RUN_DIR/logs/${scenario}_run${run_number}_start.log" 2>&1
    local startup_success=$?
    local end_startup=$(date +%s.%N)
    local startup_time=$(echo "$end_startup - $start_startup" | bc)
    cd - > /dev/null
    
    # Ready time (wait for service ready)
    local start_ready=$(date +%s.%N)
    sleep 5  # TODO: Implementare health check specifico
    local end_ready=$(date +%s.%N)
    local ready_time=$(echo "$end_ready - $start_ready" | bc)
    
    local total_time=$(echo "$end_ready - $start_total" | bc)
    
    # Save metrics
    cat > "$output_file" <<EOF
{
    "scenario": "$scenario",
    "run_number": $run_number,
    "timestamp": "$(date -Iseconds)",
    "build_time": $build_time,
    "build_success": $([ $build_success -eq 0 ] && echo "true" || echo "false"),
    "startup_time": $startup_time,
    "startup_success": $([ $startup_success -eq 0 ] && echo "true" || echo "false"),
    "ready_time": $ready_time,
    "total_time": $total_time
}
EOF
    
    log "Deployment timing: build=${build_time}s, startup=${startup_time}s, ready=${ready_time}s, total=${total_time}s"
}

# Raccolta metriche risorse in background
collect_resource_metrics() {
    local scenario=$1
    local run_number=$2
    local duration=$3
    local output_file="$RUN_DIR/metrics/${scenario}_run${run_number}_resources.csv"
    
    log "Collecting resource metrics for ${duration}s..."
    
    # Header CSV
    echo "timestamp,container,cpu_percent,memory_used_mb,memory_limit_mb,network_rx,network_tx" > "$output_file"
    
    local end_time=$(($(date +%s) + duration))
    
    while [ $(date +%s) -lt $end_time ]; do
        timestamp=$(date +%s.%N)
        
        # docker stats single shot
        docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | tail -n +2 | while read -r line; do
            container=$(echo "$line" | awk '{print $1}')
            cpu=$(echo "$line" | awk '{print $2}' | tr -d '%')
            mem_usage=$(echo "$line" | awk '{print $3}' | tr -d 'MiB')
            mem_limit=$(echo "$line" | awk '{print $5}' | tr -d 'MiB')
            net_rx=$(echo "$line" | awk '{print $6}' | tr -d 'kB')
            net_tx=$(echo "$line" | awk '{print $8}' | tr -d 'kB')
            
            echo "$timestamp,$container,$cpu,$mem_usage,$mem_limit,$net_rx,$net_tx" >> "$output_file"
        done
        
        sleep 0.5  # Sample every 500ms
    done
    
    log "Resource metrics collected"
}

# Esecuzione attacco
execute_attack() {
    local scenario=$1
    local run_number=$2
    
    log "Executing attack for $scenario..."
    
    cd "public/labs/$scenario"
    
    # Controlla se esiste comando auto-attack
    if grep -q "^auto-attack:" Makefile 2>/dev/null; then
        make auto-attack >> "$RUN_DIR/logs/${scenario}_run${run_number}_attack.log" 2>&1
        local attack_result=$?
    else
        # Fallback: comando generico attack se esiste
        if grep -q "^attack:" Makefile 2>/dev/null; then
            make attack >> "$RUN_DIR/logs/${scenario}_run${run_number}_attack.log" 2>&1
            local attack_result=$?
        else
            log_warn "No auto-attack or attack target found in Makefile"
            local attack_result=0
        fi
    fi
    
    cd - > /dev/null
    
    return $attack_result
}

# Raccolta capture packets
collect_captures() {
    local scenario=$1
    local run_number=$2
    local capture_dir="$RUN_DIR/captures/${scenario}_run${run_number}"
    
    log "Collecting packet captures..."
    
    mkdir -p "$capture_dir"
    
    # Copia latest capture da Snort
    if [ -d "captures" ]; then
        latest_capture=$(ls -td captures/*/ 2>/dev/null | head -n1)
        if [ -n "$latest_capture" ]; then
            cp -r "$latest_capture"* "$capture_dir/" || true
            log "Captures copied from $latest_capture"
        fi
    fi
    
    # Copia alert.log di Snort se disponibile
    if docker exec snort test -f /var/log/snort/alert 2>/dev/null; then
        docker exec snort cat /var/log/snort/alert > "$capture_dir/alert.log" || true
    fi
}

# Verifica detection IDS
check_ids_detection() {
    local scenario=$1
    local run_number=$2
    local capture_dir="$RUN_DIR/captures/${scenario}_run${run_number}"
    
    log "Checking IDS detection..."
    
    local alert_count=0
    if [ -f "$capture_dir/alert.log" ]; then
        alert_count=$(grep -c "^\[\*\*\]" "$capture_dir/alert.log" 2>/dev/null || echo 0)
    fi
    
    log "IDS alerts found: $alert_count"
    
    # Save detection result
    echo "{\"scenario\": \"$scenario\", \"run\": $run_number, \"alerts_count\": $alert_count, \"detected\": $([ $alert_count -gt 0 ] && echo 'true' || echo 'false')}" \
        > "$RUN_DIR/metrics/${scenario}_run${run_number}_detection.json"
    
    return $([ $alert_count -gt 0 ] && echo 0 || echo 1)
}

# Esecuzione singolo run di uno scenario
run_single_experiment() {
    local scenario=$1
    local run_number=$2
    
    log "========================================="
    log "Scenario: $scenario | Run: $run_number/$NUM_RUNS"
    log "========================================="
    
    local success=true
    
    # 1. Cleanup
    cleanup_environment
    
    # 2. Deployment timing
    measure_deployment_timing "$scenario" "$run_number" || success=false
    
    # 3. Start resource monitoring in background
    collect_resource_metrics "$scenario" "$run_number" 60 &
    local monitor_pid=$!
    
    # 4. Execute attack
    if execute_attack "$scenario" "$run_number"; then
        log "Attack executed successfully"
    else
        log_error "Attack execution failed"
        success=false
    fi
    
    # 5. Wait for monitoring to complete
    wait $monitor_pid || true
    
    # 6. Collect captures and alerts
    collect_captures "$scenario" "$run_number"
    
    # 7. Check IDS detection
    if check_ids_detection "$scenario" "$run_number"; then
        log "Attack detected by IDS"
    else
        log_warn "Attack NOT detected by IDS"
    fi
    
    # 8. Cleanup
    cleanup_environment
    
    # 9. Save run summary
    cat > "$RUN_DIR/metrics/${scenario}_run${run_number}_summary.json" <<EOF
{
    "scenario": "$scenario",
    "run_number": $run_number,
    "timestamp": "$(date -Iseconds)",
    "success": $([ "$success" = true ] && echo "true" || echo "false")
}
EOF
    
    if [ "$success" = true ]; then
        log "${GREEN}Run completed successfully${NC}"
    else
        log_error "Run completed with errors"
    fi
    
    return $([ "$success" = true ] && echo 0 || echo 1)
}

# Esecuzione tutti i run per tutti gli scenari
run_all_experiments() {
    local scenarios=$(get_scenarios)
    local total_scenarios=$(echo "$scenarios" | wc -l)
    local scenario_count=0
    
    log "Starting experiments: $total_scenarios scenario(s) × $NUM_RUNS runs = $((total_scenarios * NUM_RUNS)) total runs"
    
    for scenario in $scenarios; do
        scenario_count=$((scenario_count + 1))
        log ""
        log "========================================="
        log "SCENARIO $scenario_count/$total_scenarios: $scenario"
        log "========================================="
        
        local success_count=0
        local fail_count=0
        
        for run in $(seq 1 $NUM_RUNS); do
            if run_single_experiment "$scenario" "$run"; then
                success_count=$((success_count + 1))
            else
                fail_count=$((fail_count + 1))
            fi
            
            # Pausa tra run per stabilizzare sistema
            sleep 2
        done
        
        log "Scenario $scenario completed: $success_count/$NUM_RUNS successful"
        
        # Save scenario summary
        cat > "$RUN_DIR/analysis/${scenario}_summary.json" <<EOF
{
    "scenario": "$scenario",
    "total_runs": $NUM_RUNS,
    "successful_runs": $success_count,
    "failed_runs": $fail_count,
    "success_rate": $(echo "scale=4; $success_count / $NUM_RUNS" | bc)
}
EOF
    done
}

# Analisi statistica aggregata
run_statistical_analysis() {
    log ""
    log "========================================="
    log "Running statistical analysis..."
    log "========================================="
    
    # TODO: Chiamare script Python per analisi statistica
    # python3 scripts/statistical_analysis.py "$RUN_DIR"
    
    log "Statistical analysis completed (placeholder)"
}

# Generazione report
generate_report() {
    log ""
    log "========================================="
    log "Generating final report..."
    log "========================================="
    
    local report_file="$RUN_DIR/REPORT.md"
    
    cat > "$report_file" <<EOF
# Experimental Results Report

**Generated**: $(date -Iseconds)  
**Number of runs per scenario**: $NUM_RUNS  
**Output directory**: $RUN_DIR

## Scenarios Tested

$(get_scenarios)

## Summary

EOF
    
    # Aggiungi summary per scenario
    for scenario in $(get_scenarios); do
        if [ -f "$RUN_DIR/analysis/${scenario}_summary.json" ]; then
            echo "### $scenario" >> "$report_file"
            cat "$RUN_DIR/analysis/${scenario}_summary.json" >> "$report_file"
            echo "" >> "$report_file"
        fi
    done
    
    cat >> "$report_file" <<EOF

## Next Steps

1. Run statistical analysis: \`python3 scripts/statistical_analysis.py $RUN_DIR\`
2. Generate plots: \`python3 scripts/generate_plots.py $RUN_DIR\`
3. Review detailed logs in \`$RUN_DIR/logs/\`

EOF
    
    log "Report generated: $report_file"
}

# Main execution
main() {
    log "========================================="
    log "RTC-Attacks Automated Experimental Runner"
    log "========================================="
    
    init_experiment
    
    run_all_experiments
    
    run_statistical_analysis
    
    generate_report
    
    log ""
    log "${GREEN}=========================================${NC}"
    log "${GREEN}All experiments completed!${NC}"
    log "${GREEN}=========================================${NC}"
    log "Results available in: $RUN_DIR"
}

# Trap per cleanup in caso di interruzione
trap cleanup_environment EXIT

main "$@"
