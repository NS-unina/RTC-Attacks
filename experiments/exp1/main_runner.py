from pathlib import Path

import typer
from experiments.exp1.runner import run_experiment


app = typer.Typer()




@app.command()
def main(
    scenario_id: int = 1,
    instance: int = 1,
    repetition: int = 1,
    output_dir: Path = Path(Path.cwd() / "results" / "exp1"),
    enable_ids: bool = False,
):
    """Run a single lab scenario."""
    run_experiment(scenario_id, instance, enable_ids)


    

    

if __name__ == "__main__":
    app()