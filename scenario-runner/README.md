# scenario-runner

Small runner for RTC-Attacks lab scenarios.

It executes `make auto-attack` with isolated `INSTANCE` values and supports only
the launch modes used by the experiments:

- `staggered` (staircase): one launch every configured interval
- `spike`: launch all instances at once

## Install

```bash
cd scenario-runner
poetry install
```

## Usage

List available scenario IDs:

```bash
poetry run scenario-runner list-scenarios --labs-dir ../public/labs
```

Run staircase (scenario 4, every 45s, up to 10 instances):

```bash
poetry run scenario-runner run \
  --strategy staggered \
  --scenario 4 \
  --max-instances 10 \
  --interval-sec 45
```

Run spike test (scenario 4, 8 simultaneous instances):

```bash
poetry run scenario-runner run \
  --strategy spike \
  --scenario 4 \
  --max-instances 8
```

Generated reports are saved under `runner-results/` by default.


Stop all running scenarios (runs `make stop` on all labs):

```bash
poetry run scenario-runner stop
```

The stop command automatically targets `default` and any active numeric instances
(for example `_1`, `_2`) detected from running Compose projects.

Equivalent global flag:

```bash
poetry run scenario-runner --stop-all
```

Stop a specific scenario only:

```bash
poetry run scenario-runner stop --scenario 4
```
