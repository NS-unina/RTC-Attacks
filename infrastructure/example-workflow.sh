#!/bin/bash
# Example workflow for reproducible experiments using VM infrastructure

set -e

# Configuration
INSTANCES=(0 1 2)  # VMs to use
SNAPSHOT_NAME="experiment-baseline"

echo "=== Reproducible Experiment Workflow ==="
echo ""

# Step 1: Create baseline snapshots
echo "[1/5] Creating baseline snapshots..."
for instance in "${INSTANCES[@]}"; do
    echo "  - Snapshotting rtc-vm-$instance"
    make -C infrastructure snapshot instance=$instance name=$SNAPSHOT_NAME
done
echo ""

# Step 2: Deploy experiments to VMs
echo "[2/5] Deploying experiments..."
for instance in "${INSTANCES[@]}"; do
    echo "  - Deploying to rtc-vm-$instance"
    # Example: copy experiment code to VM
    multipass transfer experiments/ rtc-vm-$instance:/home/ubuntu/
done
echo ""

# Step 3: Run experiments in parallel
echo "[3/5] Running experiments in parallel..."
for instance in "${INSTANCES[@]}"; do
    (
        echo "  - Starting experiment on rtc-vm-$instance"
        multipass exec rtc-vm-$instance -- bash -c "\
            cd /home/ubuntu/experiments && \
            make exp1-baseline SCENARIOS=1 MONITORING=on REPETITIONS=3 > /tmp/exp-$instance.log 2>&1"
        echo "  - rtc-vm-$instance completed"
    ) &
done

# Wait for all experiments to complete
wait
echo "  All experiments completed"
echo ""

# Step 4: Collect results
echo "[4/5] Collecting results..."
mkdir -p results/distributed-run-$(date +%Y%m%d-%H%M%S)
for instance in "${INSTANCES[@]}"; do
    echo "  - Collecting from rtc-vm-$instance"
    multipass transfer rtc-vm-$instance:/home/ubuntu/experiments/results/ \
        results/distributed-run-$(date +%Y%m%d-%H%M%S)/instance-$instance/
done
echo ""

# Step 5: Restore to baseline for next run
echo "[5/5] Restoring VMs to baseline state..."
for instance in "${INSTANCES[@]}"; do
    echo "  - Restoring rtc-vm-$instance"
    make -C infrastructure restore instance=$instance name=$SNAPSHOT_NAME
done
echo ""

echo "=== Workflow completed ==="
echo "Results collected in: results/distributed-run-$(date +%Y%m%d-%H%M%S)/"
echo "VMs restored to baseline state"
