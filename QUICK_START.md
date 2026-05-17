# Quick Start

Use this repository in Suricata-only mode for experiments.

## 1) Run an experiment

The experiment runners start and stop Suricata when `MONITORING=on`.

### Experiment 1: baseline

```bash
make exp1-baseline SCENARIOS=1 REPETITIONS=1 MONITORING=on
```

### Experiment 2: scalability

```bash
make exp2-scalability N_USERS_STEPS=1,5 SCENARIO=4 MONITORING=on
```

### Experiment 3: robustness

```bash
make exp3-robustness LOAD_LEVELS=0,2 PROBE_SCENARIO=7 BACKGROUND_SCENARIO=4
```

## 2) Stop IDS capture if you interrupted a run

```bash
make stop-suricata
```

## 3) Inspect results

All active experiment outputs are under:

- `experiments/results/`

Detailed operational guide:

- `docs/EXPERIMENTS.md`
