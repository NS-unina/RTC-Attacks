import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
import experiments.config as cfg
from experiments.exp1.runner import LABS_STATE, async_experiment_wrapper

app = FastAPI()

from fastapi.responses import PlainTextResponse
from experiments.infra.ids import IdsController

from experiments.infra.capture import CaptureStore

capture_store = CaptureStore(repo_root=cfg.REPO_ROOT)

def ok_response(message: str, command_triggered: str = "") -> dict:
    return {
        "status": "ok",
        "message": message,
        "command_triggered": command_triggered
    }


class ExperimentRequest(BaseModel):
    scenario_id: int = 1
    instance: int = 1
    repetition: int = 1



class BuildAlertsRequest(BaseModel):
    # Calcolato dinamicamente ogni volta che crei un oggetto
    capture_path: str = Field(default_factory=lambda: capture_store.latest_capture_root() / "pcap")
    # Inizializziamo a None o str vuota, verrà sovrascritto dal validator
    experiment: int = 1
    repetition: int = 1
    alerts_file: Path = None  

    @model_validator(mode="after")
    def set_alerts_file(self):
        if self.alerts_file is None:
            # Qui hai accesso a self.scenario_id, self.instance, ecc.
            path_str = cfg.get_repetition_dir(self.experiment, self.repetition) / "alerts.json"
            self.alerts_file = Path(path_str)
        return self



@app.get("/ids/start")
def start_ids():
    try: 
        ids_controller = IdsController()
        ids_controller.start()
        return ok_response("IDS started successfully", command_triggered="make start-suricata")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start IDS: {str(e)}")


@app.get("/ids/stop")
def stop_ids():
    try:
        ids_controller = IdsController()
        ids_controller.stop()
        return ok_response("IDS stopped successfully", command_triggered="make stop-suricata")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop IDS: {str(e)}")


@app.post("/ids/build-alerts")
def build_alerts(request: BuildAlertsRequest):
    try:
        capture_path = request.capture_path
        alerts_file = request.alerts_file
        ids_controller = IdsController()
        result = ids_controller.build_alerts(Path(capture_path), Path(alerts_file))
        if result.returncode == 0:
            return ok_response("Alerts built successfully", command_triggered=result.cmd)
        else:
            raise HTTPException(status_code=500, detail=f"Failed to build alerts: {result.stderr}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error building alerts: {str(e)}")


@app.post("/experiments/start")
async def start_experiment(req: ExperimentRequest):
    key = (req.scenario_id, req.instance)
    
    # Controllo di unicità: errore se la combinazione esatta è già in esecuzione
    if LABS_STATE.get(key) == "running":
        raise HTTPException(
            status_code=400, 
            detail=f"Scenario {req.scenario_id} con Istanza {req.instance} è già in esecuzione!"
        )
    
    # Avvia la coroutine in background senza bloccare la risposta HTTP
    asyncio.create_task(
        async_experiment_wrapper(
            scenario_id=req.scenario_id,
            instance=req.instance,
            repetition=req.repetition,
        )
    )
    
    return {
        "status": "triggered",
        "scenario_id": req.scenario_id,
        "instance": req.instance,
        "message": "Laboratorio avviato in background."
    }

@app.get("/experiments/logs/{scenario_id}/{instance}", response_class=PlainTextResponse)
async def get_experiment_logs(scenario_id: int, instance: int, repetition: int = 1):
    """
    Riconosce il percorso dinamico del run e restituisce l'execution.log 
    come testo semplice leggibile direttamente dal browser o tramite cURL.
    """
    try:
        # Ricostruiamo lo stesso identico percorso usato durante l'avvio
        run_dir = cfg.setup_run_dir(
            cfg.ExperimentsNumbers.BASELINE.value, 
            scenario_id, 
            instance, 
            repetition
        )
        log_path = run_dir / "execution.log"
        
        if not log_path.exists():
            return f"--- [INFO] Il file di log non esiste ancora per lo Scenario {scenario_id}, Istanza {instance}. Il laboratorio potrebbe essere in fase di inizializzazione o l'IDS sta scaldando i motori. ---"
            
        # Legge e restituisce il contenuto del file di log
        return log_path.read_text(encoding="utf-8")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante la lettura del log: {str(e)}")

@app.get("/experiments/status")
async def get_all_status():
    """Ritorna lo stato di tutti gli scenari e istanze configurati."""
    # Trasforma la chiave tupla in una stringa leggibile per il JSON di output
    return {
        f"scenario_{sid}_instance_{inst}": status 
        for (sid, inst), status in LABS_STATE.items()
    }


@app.get("/experiments/status/{scenario_id}/{instance}")
async def get_single_status(scenario_id: int, instance: int):
    """Ritorna lo stato di un singolo accoppiamento specifico."""
    key = (scenario_id, instance)
    status = LABS_STATE.get(key, "not_running")
    return {
        "scenario_id": scenario_id,
        "instance": instance,
        "status": status
    }
