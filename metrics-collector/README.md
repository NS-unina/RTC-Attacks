# metrics-collector

Reusable containerized metrics collector for Docker and Compose stacks.

## Image

- `daindragon2/experimental-metrics:latest`

## Commands

- `metrics-collector deployment-times`
- `metrics-collector cpu-memory-utilization`
- `metrics-collector network-latency-overhead`

All commands require:

- `--dir PATH`

Common options:

- `--recursive`: recursively scan subfolders
- `--only-compose`: collect only compose-defined services
- `--only-container NAME`: collect only one container/service

## Build and Push

```bash
cd metrics-collector
make build
make push
```

## Run in Container

Deployment metrics:

```bash
cd metrics-collector
make run PROJECT_FOLDER=/absolute/path/to/project
```

CPU/memory metrics:

```bash
make run-cpu-memory PROJECT_FOLDER=/absolute/path/to/project
```

The generated `cpu_memory_*.csv/.json` now includes:

- Container-level rows (`scope=container`) with CPU, memory, and disk I/O (`disk_io_*_bps`)
- One host aggregate row (`scope=host`, `container=__host__`) with totals across all running stack containers

Network metrics:

```bash
make run-network PROJECT_FOLDER=/absolute/path/to/project
```

Optional network plan file for explicit probes:

```json
[
  {
    "container": "attacker",
    "probed_services": [
      { "container": "freeswitch", "port": "5060", "type": "tcp" },
      { "container": "sip-cli-1001", "port": "5061", "type": "udp" }
    ]
  }
]
```

Use with:

```bash
make run-network PROJECT_FOLDER=/absolute/path NETWORK_PLAN=/absolute/path/network_plan.json
```

Network probing behavior:

- Service container names from `network_plan.json` are resolved to container IP addresses through Docker inspection
- Without `--network-plan`: ICMP-only probing is performed (`ping`), no TCP/UDP service probes are executed
- ICMP probe: `ping` from source `container` to each resolved target IP
- Service probe (TCP): host-side `nmap -sT -p <port>` (TCP three-way connect semantics)
- Service probe (UDP): host-side `sudo nmap -sU -p <port>`
- Output includes:
  - one ICMP row per source-target pair (`protocol=icmp`, `port=null`)
  - one service row per probe definition (`protocol=tcp|udp`, `port=<configured port>`)
  - `probe_origin=source_container|host_runtime` to clarify where each probe was executed

Note:

- `nmap` must be installed in the metrics-collector runtime environment (host or collector container).
- `sudo` must be configured to allow UDP scans (`sudo nmap -sU`) in non-interactive runs.
- `type` in each probe is optional and defaults to `tcp`.
- TCP/UDP rows are marked with full loss when the configured `<port>/<protocol>` is not open.

## Discovery and Priority Rules

Default behavior:

1. If a folder has a Compose file and Dockerfiles, Compose services are prioritized.
2. Extra Dockerfiles not referenced by Compose are still included.
3. If no Compose file exists, standalone Dockerfiles are used.
4. Recursive scan is disabled unless `--recursive` is used.

## Output

For each stack, results are saved under:

- `<stack_path>/metrics/*.json`
- `<stack_path>/metrics/*.csv`

JSON output for CPU/Memory and Network commands includes:

- Top-level sampling metadata (`sampling_interval_sec`, command-specific metadata)
- `metrics` list with aggregated values
- Per-row sample series (timestamps and raw sampled values) used to compute the aggregates

## Timing Semantics

- `T_build`: from `make rebuild` (per service when possible)
- `T_startup`: from `make run` start until container is running/healthy and `make is-available` passes
- `T_total`: `T_build + T_startup`
- `T_ready`: until `make dry-run` returns ready

## Attack Phase Semantics

For CPU/Memory and Network commands, attack phase starts before `make auto-attack` and ends when `make auto-attack` completes.
