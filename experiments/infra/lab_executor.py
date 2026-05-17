"""Lab execution: launch scenarios and collect IPC events.

Minimal implementation extracted from scenario-runner.
Single-run focus: experiments execute one lab at a time.
"""

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from experiments.core.timing import utc_now_iso
from pathlib import Path
from typing import Any






class LabExecution:
    """Execute a single lab and collect IPC events."""
    
    def __init__(self, lab_path: Path, scenario_id: int, instance: int, output_dir: Path):
        self.lab_path = lab_path
        self.scenario_id = scenario_id
        self.instance = instance
        self.output_dir = output_dir
        
        # Use /tmp for socket to avoid path length issues
        
    
    def run(self) -> tuple[int, list[dict[str, Any]]]:
        """Execute lab and return (exit_code, ipc_events)."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Clean up any stale socket
        self.socket_path.unlink(missing_ok=True)
        
        # Start IPC server
        self._start_ipc_server()
        
        try:
            # Path to IPC client script
            ipc_client = Path(__file__).parent / "ipc_send.py"
            
            # Execute make auto-attack
            # The Makefile expects RTC_EVENT to be a command/script path
            # The script expects RTC_EVENT env var to contain the socket path
            env = {
                **os.environ,
                "RTC_EVENT": str(self.socket_path),  # Socket path for ipc_send.py to use
            }

            cmd = [
                "make",
                "start",
                f"SCENARIO={self.scenario_id}",
                f"INSTANCE={self.instance}",

            ]
            
            # cmd = [
            #     "make",
            #     "auto-attack",
            #     f"INSTANCE={self.instance}",
            #     f"SCENARIO={self.scenario_id}",
            #     f"RTC_EVENT={ipc_client}",  # Script path for Makefile to execute
            # ]
            
            with self.log_file.open("w", encoding="utf-8") as log:
                proc = subprocess.run(
                    cmd,
                    cwd=self.lab_path,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            
            return proc.returncode, self._events
        
        finally:
            self._stop_ipc_server()
    


def execute_lab(
    labs_dir: Path,
    scenario_id: int,
    instance: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Execute a single lab scenario.
    
    Returns:
        {
            "scenario_id": int,
            "instance": str,
            "exit_code": int,
            "success": bool,
            "start_utc": str,
            "end_utc": str,
            "duration_sec": float,
            "ipc_events": list[dict],
            "log_path": str,
        }
    """
    labs = discover_labs(labs_dir)
    
    if scenario_id not in labs:
        raise ValueError(f"Lab for scenario {scenario_id} not found")
    
    lab_path = labs[scenario_id]
    exec_dir = output_dir / f"run_{utc_now_iso().replace(':', '').replace('-', '').replace('.', '_')}"
    
    executor = LabExecution(lab_path, scenario_id, instance, exec_dir)
    
    start = time.perf_counter()
    start_utc = utc_now_iso()
    
    exit_code, events = executor.run()
    
    end_utc = utc_now_iso()
    duration = time.perf_counter() - start
    
    return {
        "scenario_id": scenario_id,
        "instance": str(instance),
        "lab_path": str(lab_path),
        "exit_code": exit_code,
        "success": exit_code == 0,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "duration_sec": duration,
        "ipc_events": events,
        "log_path": str(executor.log_file),
        "output_dir": str(exec_dir),
    }
