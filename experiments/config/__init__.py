"""Configuration utilities for experiment scripts."""

from __future__ import annotations
from enum import Enum
from pathlib import Path
import sys

import json
from typing import Any, TypedDict

CONFIG_DIR = Path(__file__).parent
DEFAULTS_FILE = CONFIG_DIR / "defaults.json"
REPO_ROOT = Path(__file__).resolve().parents[2]                                                                                                                                                                          
MIN_WAITING_TIME = 2  # seconds
MAX_WAITING_TIME = 10  # seconds
IDS_WARMUP_SEC: float = 5
TIMEZONE = "Europe/Rome"

class ExperimentsNumbers(Enum):
    BASELINE = 1
    VERTICAL_SCALABILITY = 2
    IDS_IMPACT_LOAD = 3

if str(REPO_ROOT) not in sys.path:                                                                                                                                                                                      
    sys.path.insert(0, str(REPO_ROOT))                                                                                                                                                                   

RESULTS_DIR = REPO_ROOT / "results"

def setup_run_dir(exp_no: int, repetition: int, scenario_id: int, instance: int) -> Path:
    """Create and return a directory for storing results of a specific run."""
    run_dir = RESULTS_DIR / f"exp_{exp_no}" / f"rep_{repetition}" / f"scenario_{scenario_id}" / f"instance_{instance}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

_config_cache: dict[str, Any] | None = None

def get_experiment_dir(exp_no: int): 
    """Get the base directory for a specific experiment number."""
    exp_dir = RESULTS_DIR / f"exp_{exp_no}"
    exp_dir.mkdir(parents=True, exist_ok=True)
    return exp_dir

def get_repetition_dir(exp_no: int, repetition: int):
    """Get the directory for a specific experiment number and repetition."""
    rep_dir = get_experiment_dir(exp_no) / f"rep_{repetition}"
    return rep_dir

def get_run_dir(exp_no: int, repetition: int, scenario_id: int, instance: int) -> Path:
    """Convenience function to get the run directory for a specific experiment configuration."""
    run_dir = RESULTS_DIR / f"exp_{exp_no}" / f"rep_{repetition}" / f"scenario_{scenario_id}" / f"instance_{instance}"
    return run_dir


def load_defaults() -> dict[str, Any]:
    """Load default configuration from defaults.json (cached)."""
    global _config_cache
    if _config_cache is None:
        _config_cache = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
    return _config_cache


def get(path: str, default: Any = None) -> Any:
    """Get configuration value by dot-separated path (e.g., 'timing.alert_window_post_sec')."""
    config = load_defaults()
    keys = path.split(".")
    value = config
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return default
    return value if value is not None else default



def discover_labs(labs_dir: Path = Path.cwd() / "public" / "labs" ) -> dict[int, Path]:
    """Find available labs by scanning directory names.
    
    Returns: {scenario_id: lab_path}
    Example: {1: Path(".../1_2_sip_spoofing_dos_freeswitch")}
    """
    labs = {}
    
    for entry in sorted(labs_dir.iterdir()):
        if not entry.is_dir() or not (entry / "Makefile").exists():
            continue
        
        # Extract scenario IDs from directory name (e.g., "1_2_name" -> [1, 2])
        ids = []
        for token in entry.name.split("_"):
            if token.isdigit():
                ids.append(int(token))
            else:
                break
        
        for scenario_id in ids:
            if scenario_id in labs:
                raise ValueError(f"Duplicate scenario_id {scenario_id}")
            labs[scenario_id] = entry.resolve()
    
    return labs

def get_lab_path(scenario_id: int, labs_dir: Path = REPO_ROOT / "public" / "labs") -> Path:
    """Get lab path for a given scenario ID."""
    labs = discover_labs(labs_dir)
    if scenario_id not in labs:
        raise ValueError(f"Lab for scenario {scenario_id} not found")
    return labs[scenario_id]