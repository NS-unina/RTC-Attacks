import typer
from typing_extensions import Annotated

from experiments.infra.pushgateway import PushGateway
app = typer.Typer(help="CLI for synchronizing lab events with Prometheus.")

@app.command()
def track(
    event_type: Annotated[str, typer.Argument(help="Event type (e.g., attack_start, attack_end, lab_ready, lab_stop)")],
    stack: Annotated[str, typer.Option(help="Current Stack ID")] = "unknown",
    scenario: Annotated[str, typer.Option(help="Scenario ID")] = "unknown",
    instance: Annotated[str, typer.Option(help="Instance name or ID")] = "default",
    attack: Annotated[str, typer.Option(help="Name of the executed attack")] = "none",
    pushgateway_url: Annotated[str, typer.Option(help="Prometheus Pushgateway address")] = "http://10.9.0.5:9091"
):
    """
    Pushes the lab lifecycle state to the Prometheus Pushgateway.
    """

    pw = PushGateway()
    # # 2. Capture the exact execution timestamp (Unix epoch time)
    # current_timestamp = time.time()

    # # Create an isolated Prometheus registry
    # registry = CollectorRegistry()

    # # Choose the metric name based on the context type
    # metric_name = "lab_attack_status" if 'attack' in event_type else "lab_lifecycle_status"

    # # Define the Gauge with its corresponding labels
    # g = Gauge(
    #     metric_name,
    #     'Tracking lab lifecycle events via Typer CLI',
    #     ['stack', 'scenario', 'instance', 'attack', 'event'],
    #     registry=registry
    # )

    # # 3. Map the labels and set the value to the current timestamp.
    # # This stores the exact execution time inside the TSDB.
    # g.labels(
    #     stack=stack,
    #     scenario=scenario,
    #     instance=instance,
    #     attack=attack,
    #     event=event_type
    # ).set(current_timestamp) 

    # # Push to the gateway
    # try:
    #     push_to_gateway(pushgateway_url, job='lab_events', registry=registry)
    #     typer.secho(f"🚀 [SUCCESS] Event '{event_type}' recorded in TSDB at timestamp {current_timestamp}", fg=typer.colors.GREEN)
    # except Exception as e:
    #     typer.secho(f"❌ [ERROR] Failed to push to Pushgateway: {e}", fg=typer.colors.RED, err=True)
    #     raise typer.Exit(code=1)

if __name__ == "__main__":
    app()