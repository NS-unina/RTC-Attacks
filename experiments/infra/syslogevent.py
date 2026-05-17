import json
import logging
from pathlib import Path
import sys
import time
from enum import StrEnum

from experiments import config as cfg
from experiments.core.timing import utc_now_iso_micro


class ScenarioEvent(StrEnum):
    LAB_START = "lab_start"
    LAB_READY = "lab_ready"
    LAB_STOP = "lab_stop"
    ATTACK_START = "attack_start"
    ATTACK_END = "attack_end"
    ATTACK_SUCCESS = "attack_success"
    ATTACK_FAILURE = "attack_failure"


class SyslogGateway:
    def __init__(
        self,
        stack: str = "unknown",
        scenario_id: str = "0",
        instance: str = "default",
        log_file_path: Path = Path.cwd() / "logs/experiment_events.log"
    ):
        self.stack = stack
        self.scenario = scenario_id
        self.instance = instance
        self.log_file_path = log_file_path

        # Configura un logger dedicato per gli eventi strutturati
        self.logger = logging.getLogger("ExperimentLogger")
        self.logger.setLevel(logging.INFO)
        
        # Evita duplicati se la classe viene reinizializzata
        if not self.logger.handlers:
            try:
                file_handler = logging.FileHandler(self.log_file_path)
                # Formato pulito: scriverà solo il messaggio generato (che sarà un JSON)
                file_handler.setFormatter(logging.Formatter('%(message)s'))
                self.logger.addHandler(file_handler)
            except Exception as e:
                print(f"[ERROR] Failed to initialize log file handler: {e}", file=sys.stderr)

    def _log_event_to_loki(self, event_type: ScenarioEvent):
        """Genera un log strutturato in JSON che Alloy leggerà."""
        log_data = {
            "timestamp": utc_now_iso_micro(),
            "event": event_type.value,
            "stack": self.stack,
            "scenario": self.scenario,
            "instance": self.instance,
            "message": f"Scenario event triggered: {event_type.value.upper()} on stack {self.stack}"
        }
        
        try:
            # Scrive la riga nel file di log
            self.logger.info(json.dumps(log_data))
            print(f"[SUCCESS] Event '{event_type.value}' logged successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to write event log: {e}", file=sys.stderr)

    def _push_event(self, event_type: ScenarioEvent):
        # Logga l'evento su file (per Alloy -> Loki)
        self._log_event_to_loki(event_type)

    def push_lab_start(self): self._push_event(ScenarioEvent.LAB_START)
    def push_lab_ready(self): self._push_event(ScenarioEvent.LAB_READY)
    def push_lab_stop(self): self._push_event(ScenarioEvent.LAB_STOP)
    def push_attack_start(self): self._push_event(ScenarioEvent.ATTACK_START)
    def push_attack_end(self): self._push_event(ScenarioEvent.ATTACK_END)
    def push_attack_success(self): self._push_event(ScenarioEvent.ATTACK_SUCCESS)
    def push_attack_failure(self): self._push_event(ScenarioEvent.ATTACK_FAILURE)