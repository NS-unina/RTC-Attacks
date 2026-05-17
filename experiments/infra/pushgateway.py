import sys
import time
from enum import StrEnum

from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from experiments import config as cfg


class ScenarioEvent(StrEnum):
    LAB_START = "lab_start"
    LAB_READY = "lab_ready"
    LAB_STOP = "lab_stop"
    ATTACK_START = "attack_start"
    ATTACK_END = "attack_end"
    ATTACK_SUCCESS = "attack_success"
    ATTACK_FAILURE = "attack_failure"


class PushGateway:
    def __init__(
        self,
        stack: str = "unknown",
        scenario_id: str = "0",
        instance: str = "default",
    ):
        self.url = cfg.get("pushgateway", "url")["url"]
        self.stack = stack
        self.scenario = scenario_id
        self.instance = instance

        # Stato cumulativo del run:
        # {"lab_start": 1778949588.0, "lab_ready": 1778949590.0, ...}
        self.events: dict[str, float] = {}

    def _push_event(self, event_type: ScenarioEvent):
        # Salva/aggiorna il timestamp dell'evento corrente
        self.events[event_type.value] = time.time()

        registry = CollectorRegistry()

        g = Gauge(
            "lab_event_timestamp_seconds",
            "Unix timestamp of lab scenario events",
            ["event"],
            registry=registry,
        )

        # Push cumulativo: manda tutti gli eventi raccolti finora
        for event, timestamp in self.events.items():
            g.labels(event=event).set(timestamp)

        try:
            push_to_gateway(
                self.url,
                job="lab_events",
                grouping_key={
                    "stack": self.stack,
                    "scenario": self.scenario,
                    "instance": self.instance,
                },
                registry=registry,
                timeout=3,
            )
            print(f"[SUCCESS] Event '{event_type.value}' pushed.")
        except Exception as e:
            print(f"[ERROR] Failed to push to Pushgateway: {e}", file=sys.stderr)

    def push_lab_start(self):
        self._push_event(ScenarioEvent.LAB_START)

    def push_lab_ready(self):
        self._push_event(ScenarioEvent.LAB_READY)

    def push_lab_stop(self):
        self._push_event(ScenarioEvent.LAB_STOP)

    def push_attack_start(self):
        self._push_event(ScenarioEvent.ATTACK_START)

    def push_attack_end(self):
        self._push_event(ScenarioEvent.ATTACK_END)

    def push_attack_success(self):
        self._push_event(ScenarioEvent.ATTACK_SUCCESS)

    def push_attack_failure(self):
        self._push_event(ScenarioEvent.ATTACK_FAILURE)
