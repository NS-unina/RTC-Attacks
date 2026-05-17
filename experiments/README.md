# Experiments

See [docs/EXPERIMENTS.md](../docs/EXPERIMENTS.md) for the full guide.

## Structure

```
core/             ← domain constants (scenario IDs, timestamps)
infra/            ← external system adapters (IDS, scenario-runner, capture store)
pipeline/         ← PCAP → Suricata alerts → NFStream flows → labeled CSV
exp1_baseline/    ← Experiment 1: Baseline Characteristics
exp2_scalability/ ← Experiment 2: Vertical Scalability
exp3_robustness/  ← Experiment 3: Detection Robustness under Load
results/          ← all outputs (gitignored)
```

## Running the experiments

### Experiment 1 — Baseline Characteristics

Runs each scenario N times and measures detection recall, precision, and F1.

```bash
# Full run: all scenarios, 30 repetitions, monitoring enabled
make exp1-baseline REPETITIONS=30 MONITORING=on

# Quick test: single scenario, 1 repetition
make exp1-baseline SCENARIOS=6 REPETITIONS=1

# Direct invocation
python3 -m experiments.exp1_baseline.runner \
  --scenarios 1,2,3,4,5,6,7,8,9 \
  --repetitions 30 \
  --monitoring on \
  --output-dir experiments/results/exp1_baseline
```

### Experiment 2 — Vertical Scalability

Runs a staircase of user densities and measures how the system scales.

```bash
# Staircase: 1 → 5 → 10 → 20 parallel users on scenario 4
make exp2-scalability N_USERS_STEPS=1,5,10,20 SCENARIO=4 MONITORING=on

# Direct invocation
python3 -m experiments.exp2_scalability.runner \
  --n-users-steps 1,5,10,20 \
  --scenario 4 \
  --monitoring on \
  --interval-sec 45 \
  --output-dir experiments/results/exp2_scalability
```

### Experiment 3 — Detection Robustness under Load

Probes one attack scenario while a background load of varying intensity runs concurrently.

```bash
# Probe scenario 7 under background load of 0, 2, 4, 6, 8 instances of scenario 4
make exp3-robustness LOAD_LEVELS=0,2,4,6,8 PROBE_SCENARIO=7 BACKGROUND_SCENARIO=4

# Direct invocation
python3 -m experiments.exp3_robustness.runner \
  --load-levels 0,2,4,6,8 \
  --probe-scenario 7 \
  --background-scenario 4 \
  --output-dir experiments/results/exp3_robustness
```

## Results

All outputs are written under `experiments/results/`. Each run creates a timestamped subdirectory containing a `report.json` and per-repetition logs.
