from pathlib import Path
from time import sleep
import time
import experiments.config as cfg
from experiments.core import logger

import typer

from experiments.core.timing import get_random_waiting_time
from experiments.infra.capture import CaptureStore
from experiments.infra.ids import IdsController
from experiments.infra.syslogevent import SyslogGateway
from experiments.infra.makefile_runner import MakeRunner

app = typer.Typer()



def cleanup_all(ids):
    """Best-effort cleanup of all lab and IDS resources."""
    logger.info("Cleaning up lab and IDS resources...")
    # Stop IDS (best effort)
    try:
        ids.stop()
    except Exception as e:
        logger.error(f"Failed to stop IDS: {e}")

@app.command()
def main(
    scenario_id: int = 1,
    instance: int = 1,
    repetition: int = 1,
    output_dir: Path = Path(Path.cwd() / "results" / "exp1"),
    enable_ids: bool = False,
):
    """Run a single lab scenario."""
    logger.info(f"Running scenario {scenario_id} instance {instance} (results in {output_dir})")
    run_dir = cfg.setup_run_dir(cfg.ExperimentsNumbers.BASELINE.value, scenario_id, instance, repetition)
    log_path = run_dir / "execution.log"
    ids = IdsController()
    lab_path = cfg.get_lab_path(scenario_id)
    syslog_gw = SyslogGateway(stack=str(lab_path), scenario_id=str(scenario_id), 
                instance=str(instance))
    capture_store = CaptureStore(repo_root=cfg.REPO_ROOT)
    makefile_runner = MakeRunner(lab_path=lab_path, scenario_id=scenario_id, instance=instance)



    if enable_ids:
        logger.info("Starting IDS...")
        ids.start()
        time.sleep(cfg.IDS_WARMUP_SEC)

    logger.info("Starting lab and executing attack...")
    syslog_gw.push_lab_start()
    results = makefile_runner.start()
    makefile_runner.write_cli_log(log_path, results)
    syslog_gw.push_lab_ready()
    time.sleep(get_random_waiting_time(cfg.MIN_WAITING_TIME, cfg.MAX_WAITING_TIME))
    logger.info("Triggering attack...")
    syslog_gw.push_attack_start()
    results = makefile_runner.attack()
    makefile_runner.write_cli_log(log_path, results)
    syslog_gw.push_attack_end()
    time.sleep(get_random_waiting_time(cfg.MIN_WAITING_TIME, cfg.MAX_WAITING_TIME))
    logger.info("Stopping lab...")
    results = makefile_runner.stop()
    makefile_runner.write_cli_log(log_path, results)
    syslog_gw.push_lab_stop()






    
    ### ... execution 
    # sleep(2)
    # sleep(2)
    # sleep(2)
    # sleep(2)
    # # Execute lab and collect events
    # returncode, events = execute_lab(
    #     labs_dir=Path("public/labs"),
    #     scenario_id=scenario_id,
    #     instance=instance,
    #     output_dir=output_dir,
    # )
    
    # Save results
    # result_path = output_dir / f"scenario_{scenario_id}_instance_{instance}.json"
    # with result_path.open("w", encoding="utf-8") as f:
    #     json.dump({
    #         "scenario_id": scenario_id,
    #         "instance": instance,
    #         "returncode": returncode,
    #         "events": events,
    #     }, f, indent=2)
    cleanup_all(ids)
    latest_pcap_path = capture_store.latest_pcap()
    ids.build_alerts(capture_path=latest_pcap_path, alerts_file=run_dir / "alerts.json")

    

if __name__ == "__main__":
    app()