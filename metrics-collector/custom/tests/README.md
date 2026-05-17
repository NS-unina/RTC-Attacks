# metrics-collector tests

This folder contains an end-to-end Compose stack to validate the three CLI commands:

- `deployment-times`
- `cpu-memory-utilization`
- `network-latency-overhead`

## Test stack

Path: `tests/e2e-stack`

Services:

- `attacker`
- `httpd_frontend`
- `httpd_backend`
- `dns_resolver`

Network test behavior:

- Previous implementation (kept for traceability): `target` used synthetic netcat listeners on `5060/tcp` and `5061/udp`
- Updated implementation: two real `httpd` services are probed on `80/tcp`, plus one `CoreDNS` service on `53/udp`
- `attacker` uses built-in Alpine utilities (`ping`, `wget`, `nslookup`) to generate realistic ICMP/HTTP/DNS traffic
- `nmap` probes are executed host-side by the `poetry run metrics-collector ...` process
- when `--network-plan` is omitted, only ICMP rows are generated (no TCP/UDP service probing)

Example `tests/network-plan/network_plan.json`:

```json
[
  {
    "container": "attacker",
    "probed_services": [
      { "container": "httpd_frontend", "port": "80", "type": "tcp" },
      { "container": "httpd_backend", "port": "80", "type": "tcp" },
      { "container": "dns_resolver", "port": "53", "type": "udp" }
    ]
  }
]
```

`type` is optional and defaults to `tcp`.

The stack provides all required Make targets used by the collector:

- `rebuild`
- `run`
- `is-available`
- `dry-run`
- `auto-attack`
- `stop`

## Run with Poetry

From `metrics-collector/`:

```bash
poetry install

poetry run metrics-collector deployment-times \
  --dir "$(pwd)/tests/e2e-stack"

poetry run metrics-collector cpu-memory-utilization \
  --dir "$(pwd)/tests/e2e-stack" \
  --baseline-samples 5 \
  --sample-interval-sec 0.5

poetry run metrics-collector network-latency-overhead \
  --dir "$(pwd)/tests/e2e-stack" \
  --sample-interval-sec 0.5 \
  --network-plan "$(pwd)/tests/network-plan/network_plan.json"
```

## Output

Generated metrics are written to:

- `tests/e2e-stack/metrics/*.json`
- `tests/e2e-stack/metrics/*.csv`

For network metrics, each source-target pair generates protocol-specific rows:

- `protocol=icmp`, `port=null` (ping RTT/loss per source-target pair)
- `protocol=tcp|udp`, `port=<configured>` (host-side nmap RTT/loss per configured service probe)
- `probe_origin` clarifies where each probe ran (`source_container` for ICMP, `host_runtime` for service probes)

For CPU/Memory and Network JSON outputs:

- `sampling_interval_sec` is reported in the top-level JSON object
- each metric row includes sample timestamps and raw per-sample values
- aggregated/average fields are computed from those sampled series
