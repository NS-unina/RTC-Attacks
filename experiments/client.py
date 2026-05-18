import json
from typing import Optional
import requests
import typer

app = typer.Typer(help="CLI client to control and monitor the RTC-Attacks API orchestrator.")

# Configurazione di default basata sulla tua porta custom
DEFAULT_API_URL = "http://localhost:19999"


@app.command()
def start(
    scenario_id: int = typer.Option(1, "--scenario", "-s", help="ID of the scenario to execute"),
    instance: int = typer.Option(1, "--instance", "-i", help="Instance index identifier"),
    repetition: int = typer.Option(1, "--rep", "-r", help="Repetition count for the benchmark run"),
    enable_ids: bool = typer.Option(True, help="Enable or disable Suricata IDS monitoring layer"),
    output_dir: str = typer.Option("results/exp1", "--out", help="Directory where results will be stored"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--url", help="Base URL of the orchestrator API")
):
    """
    Trigger a laboratory experiment run in the background on the target VM.
    """
    url = f"{api_url}/experiments/start"
    payload = {
        "scenario_id": scenario_id,
        "instance": instance,
        "repetition": repetition,
        "enable_ids": enable_ids,
        "output_dir": output_dir
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            typer.secho(f"🚀 {data['message']}", fg=typer.colors.GREEN, bold=True)
            typer.echo(f"Triggered Command: {data['command_triggered']}")
        else:
            detail = response.json().get("detail", response.text)
            typer.secho(f"❌ API Error ({response.status_code}): {detail}", fg=typer.colors.RED, err=True)
    except requests.RequestException as e:
        typer.secho(f"💥 Failed to connect to the orchestrator at {api_url}: {e}", fg=typer.colors.RED, err=True)


@app.command()
def start_ids():
    """Start the Suricata IDS stack via API call."""
    url = f"{DEFAULT_API_URL}/ids/start"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            typer.secho(f"{data['message']}", fg=typer.colors.GREEN)
            typer.echo(f"[+] Triggered Command: {data['command_triggered']}")
        else:
            detail = response.json().get("detail", response.text)
            typer.secho(f"[-] API Error ({response.status_code}): {detail}", fg=typer.colors.RED, err=True)
    except requests.RequestException as e:
        typer.secho(f"[-] Connection failed: {e}", fg=typer.colors.RED, err=True)

@app.command()
def stop_ids():
    """Stop the Suricata IDS stack via API call."""
    url = f"{DEFAULT_API_URL}/ids/stop"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            typer.secho(f"{data['message']}", fg=typer.colors.GREEN)
            typer.echo(f"[+] Triggered Command: {data['command_triggered']}")
        else:
            detail = response.json().get("detail", response.text)
            typer.secho(f"[-] API Error ({response.status_code}): {detail}", fg=typer.colors.RED, err=True)
    except requests.RequestException as e:
        typer.secho(f"[-] Connection failed: {e}", fg=typer.colors.RED, err=True)




@app.command()
def status(
    scenario_id: Optional[int] = typer.Option(None, "--scenario", "-s", help="Filter by specific scenario ID"),
    instance: Optional[int] = typer.Option(None, "--instance", "-i", help="Filter by specific instance ID"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--url", help="Base URL of the orchestrator API")
):
    """
    Fetch the execution status of running or completed laboratory experiments.
    """
    try:
        # Se vengono passati sia scenario che istanza, interroga l'endpoint singolo
        if scenario_id is not None and instance is not None:
            url = f"{api_url}/experiments/status/{scenario_id}/{instance}"
            response = requests.get(url)
        else:
            url = f"{api_url}/experiments/status"
            response = requests.get(url)

        if response.status_code == 200:
            typer.echo(json.dumps(response.json(), indent=2))
        else:
            typer.secho(f"❌ API Error ({response.status_code}): {response.text}", fg=typer.colors.RED, err=True)
    except requests.RequestException as e:
        typer.secho(f"💥 Connection failed: {e}", fg=typer.colors.RED, err=True)


@app.command()
def build_alerts(
    scenario_id: int = typer.Option(1, "--scenario", "-s", help="Scenario ID for which to build alerts"),
    instance: int = typer.Option(1, "--instance", "-i", help="Instance ID for which to build alerts"),
    repetition: int = typer.Option(1, "--rep", "-r", help="Repetition index for log tracking"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--url", help="Base URL of the orchestrator API")
):
    """
    Trigger the IDS alert building process for a specific scenario and instance.
    """
    url = f"{api_url}/ids/build-alerts"
    payload = {
        "scenario_id": scenario_id,
        "instance": instance,
        "repetition": repetition
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            typer.secho(f"{data['message']}", fg=typer.colors.GREEN)
            typer.echo(f"[+] Triggered Command: {data['command_triggered']}")
        else:
            detail = response.json().get("detail", response.text)
            typer.secho(f"❌ API Error ({response.status_code}): {detail}", fg=typer.colors.RED, err=True)
    except requests.RequestException as e:
        typer.secho(f"💥 Connection failed: {e}", fg=typer.colors.RED, err=True)

@app.command()
def logs(
    scenario_id: int = typer.Argument(..., help="Target scenario ID"),
    instance: int = typer.Argument(..., help="Target instance ID"),
    repetition: int = typer.Option(1, "--rep", "-r", help="Repetition index for log tracking"),
    api_url: str = typer.Option(DEFAULT_API_URL, "--url", help="Base URL of the orchestrator API")
):
    """
    Stream or read the current plain-text execution logs of an isolated run.
    """
    url = f"{api_url}/experiments/logs/{scenario_id}/{instance}"
    params = {"repetition": repetition}
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            typer.echo(response.text)
        else:
            typer.secho(f"❌ API Error ({response.status_code}): {response.text}", fg=typer.colors.RED, err=True)
    except requests.RequestException as e:
        typer.secho(f"💥 Connection failed: {e}", fg=typer.colors.RED, err=True)


if __name__ == "__main__":
    app()