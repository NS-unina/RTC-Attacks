"""Experiment 2: vertical scalability.

Runs the documented staircase experiment: for each user-density step, launch
N instances of one scenario with the scenario-runner staggered strategy.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import typer

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments import config as cfg
from experiments.core.timing import utc_now_iso, utc_tag
from experiments.infra.ids import IdsController
from experiments.infra.scenario_runner import ScenarioRunnerAdapter
from experiments.infra.shell import write_cli_log


@dataclass(frozen=True)
class ScalabilityConfig:
    n_users_steps: list[int]
    scenario_id: int
    monitoring_enabled: bool
    interval_sec: float
    output_dir: Path
    ids_warmup_sec: float = 2.0
    ids_cooldown_sec: float = 2.0


@dataclass(frozen=True)
class StaircaseStepResult:
    step: int
    n_users: int
    monitoring_enabled: bool
    scenario_id: int
    runner_exit_code: int
    runner_summary_path: str
    t_ready_sec: float
    ok: bool
    error: str


def run_experiment(config: ScalabilityConfig, repo_root: Path) -> list[StaircaseStepResult]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    scenario_runner = ScenarioRunnerAdapter(repo_root)
    ids = IdsController(repo_root)

    results = [
        _run_step(step, n_users, config, scenario_runner, ids)
        for step, n_users in enumerate(config.n_users_steps, start=1)
    ]
    _write_report(config, results)
    return results


def _run_step(
    step: int,
    n_users: int,
    config: ScalabilityConfig,
    scenario_runner: ScenarioRunnerAdapter,
    ids: IdsController,
) -> StaircaseStepResult:
    step_dir = config.output_dir / f"step_{step:02d}_n{n_users}"
    runner_dir = step_dir / "runner"
    step_dir.mkdir(parents=True, exist_ok=True)

    started = perf_counter()
    summary_path = ""

    try:
        if config.monitoring_enabled:
            ids.start()
            time.sleep(config.ids_warmup_sec)

        # Change rationale: measure concurrent user density with one real staggered run.
        proc, summary_file = scenario_runner.run_staggered(
            scenario_id=config.scenario_id,
            max_instances=n_users,
            interval_sec=config.interval_sec,
            output_dir=runner_dir,
        )
        write_cli_log(step_dir / "scenario_runner_cli.log", proc)
        summary_path = str(summary_file)
        ok = proc.returncode == 0
        error = "" if ok else "scenario-runner failed"

    except Exception as exc:
        ok = False
        error = str(exc)
        proc = None

    finally:
        if config.monitoring_enabled:
            time.sleep(config.ids_cooldown_sec)
            ids.stop()

    return StaircaseStepResult(
        step=step,
        n_users=n_users,
        monitoring_enabled=config.monitoring_enabled,
        scenario_id=config.scenario_id,
        runner_exit_code=proc.returncode if proc is not None else 1,
        runner_summary_path=summary_path,
        t_ready_sec=perf_counter() - started,
        ok=ok,
        error=error,
    )


def _write_report(config: ScalabilityConfig, results: list[StaircaseStepResult]) -> None:
    payload = {
        "experiment": "exp2_scalability",
        "generated_at_utc": utc_now_iso(),
        "config": {
            "n_users_steps": config.n_users_steps,
            "scenario_id": config.scenario_id,
            "monitoring_enabled": config.monitoring_enabled,
            "interval_sec": config.interval_sec,
        },
        "results": [asdict(result) for result in results],
    }
    report_path = config.output_dir / "report.json"
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[exp2] Report written to: {report_path}")


app = typer.Typer()


@app.command()
def main(
    n_users_steps: str = typer.Option("1,5,10,20", help="Comma-separated user-density steps"),
    scenario: int = typer.Option(cfg.get("experiment2_scalability.default_scenario_id"), help="Scenario ID"),
    monitoring: str = typer.Option("on", help="Enable IDS monitoring (on/off)"),
    interval_sec: float = typer.Option(cfg.get("experiment2_scalability.interval_sec"), help="Stagger interval in seconds"),
    output_dir: str = typer.Option(None, help="Output directory (auto-generated if omitted)"),
) -> None:
    """Experiment 2: Vertical Scalability."""
    # Simplified parsing with list comprehension
    steps = [int(v.strip()) for v in n_users_steps.split(",") if v.strip()]
    
    out_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir
        else REPO_ROOT / "experiments" / "results" / "exp2_scalability" / f"run_{utc_tag()}"
    )
    
    config = ScalabilityConfig(
        n_users_steps=steps,
        scenario_id=scenario,
        monitoring_enabled=(monitoring == "on"),
        interval_sec=interval_sec,
        output_dir=out_dir,
        ids_warmup_sec=cfg.get("timing.ids_warmup_sec"),
        ids_cooldown_sec=cfg.get("timing.ids_cooldown_sec"),
    )

    for result in run_experiment(config, repo_root=REPO_ROOT):
        status = "OK" if result.ok else f"FAIL({result.error})"
        print(f"[exp2] step={result.step} n_users={result.n_users} t_ready={result.t_ready_sec:.1f}s -> {status}")


if __name__ == "__main__":
    app()
