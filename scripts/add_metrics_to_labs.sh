#!/bin/bash
# Script to add metrics collection capabilities to all labs
# This script adds the include statement for ../metrics.mk to each lab

set -e

LABS_DIR="/home/gx1/git/Unina/RTC-Attacks/public/labs"
METRICS_FILE="metrics.mk"

echo "[*] Adding metrics collection to all labs..."

# Verify metrics.mk exists in labs directory
if [ ! -f "$LABS_DIR/$METRICS_FILE" ]; then
    echo "[!] Error: $LABS_DIR/$METRICS_FILE not found"
    exit 1
fi

echo "[+] Found metrics template: $LABS_DIR/$METRICS_FILE"
echo ""

# Add include statement to each lab's Makefile
for lab in "$LABS_DIR"/*/; do
    lab_name=$(basename "$lab")
    echo "[*] Processing lab: $lab_name"
    
    # Check if Makefile exists
    if [ -f "$lab/Makefile" ]; then
        # Check if already includes metrics.mk
        if ! grep -q "include ../metrics.mk" "$lab/Makefile"; then
            echo "[+] Adding include statement to $lab_name/Makefile"
            # Add include at the end of the file
            echo "" >> "$lab/Makefile"
            echo "# Include metrics collection targets" >> "$lab/Makefile"
            echo "include ../metrics.mk" >> "$lab/Makefile"
        else
            echo "[=] $lab_name already includes ../metrics.mk"
        fi
        
        # Verify DOCKER_COMPOSE is defined
        if ! grep -q "DOCKER_COMPOSE" "$lab/Makefile"; then
            echo "[!] Warning: DOCKER_COMPOSE not found in $lab_name/Makefile"
            echo "[*] Adding default DOCKER_COMPOSE definition..."
            # Add at the beginning (after shebang if exists)
            sed -i '1s/^/DOCKER_COMPOSE := $(shell command -v docker-compose 2> \/dev\/null || echo "docker compose")\n/' "$lab/Makefile"
        fi
    else
        echo "[!] No Makefile found in $lab_name"
    fi
    
    echo ""
done

echo "[+] Metrics collection added to all labs!"
echo ""
echo "Usage in each lab:"
echo "  make metrics-help          - Show all available metrics targets"
echo "  make metrics-all           - Run complete metrics collection"
echo "  make metrics-reproducibility RUNS_COUNT=30 SCENARIO=1"
echo ""
