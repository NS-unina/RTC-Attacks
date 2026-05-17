from pathlib import Path
import typer
from typing_extensions import Annotated
from experiments.checks.attack_success_check import check_signature_in_output
from experiments.config import discover_labs
import random

from experiments.infra.makefile_runner import MakeRunner

# Inizializziamo l'app Typer
app = typer.Typer(help="Test Makefile-based lab execution")

@app.command()
def print_labs():
    labs = discover_labs()
    for scenario_id, lab_path in labs.items():
        print(f"Scenario {scenario_id}: {lab_path}")

@app.command()
def run(
    scenario_id: Annotated[int, typer.Argument(help="ID of the scenario to run")],
):
    """
    Esegue start e stop sul lab specificato.
    """
    labs = discover_labs()
    if scenario_id not in labs:
        typer.echo(f"Scenario {scenario_id} not found.")
        raise typer.Exit(1)

    lab = labs[scenario_id]

    typer.echo(f"Esecuzione lab nella cartella: {lab}")
    
    # Passiamo l'oggetto Path (già validato e assoluto) a MakeRunner
    runner = MakeRunner(lab, scenario_id=scenario_id, instance=random.randrange(100,199))
    
    typer.echo("Starting lab...")
    start_result = runner.start()
    typer.echo(f"Start result returncode: {start_result.returncode}")
    print("[STDOUT] " + start_result.stdout)
    print("[STDERR] " + start_result.stderr)
    
    typer.echo(f"Run attack...")
    attack_result = runner.attack()
    typer.echo(f"Attack result returncode: {attack_result.returncode}")
    print("[STDOUT] " + attack_result.stdout)
    print("CHECK SIGNATURE")
    print(check_signature_in_output(scenario_id, attack_result.stdout))

    typer.echo("Stopping lab...")
    stop_result = runner.stop()
    typer.echo(f"Stop result returncode: {stop_result.returncode}")

if __name__ == "__main__":
    app()