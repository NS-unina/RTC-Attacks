"""UTC timestamp helpers used across all experiment modules."""

from __future__ import annotations
from zoneinfo import ZoneInfo

import random
from datetime import datetime, timezone
from experiments import config as cfg


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string (e.g. '2026-05-15T14:00:00Z')."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_tag() -> str:
    """Return a filesystem-safe local timestamp tag (e.g. '20260515_140000')."""
    # Change rationale: run directory names should follow host local time for operator correlation.
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")

def utc_now_iso_micro() -> str:
    """
    Ritorna il timestamp UTC corrente in formato ISO-8601 con microsecondi.
    """
    tz_roma = ZoneInfo(cfg.TIMEZONE)
    return datetime.now(tz_roma).isoformat()


def fix_timestamp_to_rome_iso(ts: str) -> str:
    """
    Convert an ISO-8601 timestamp to Europe/Rome timezone, keeping the same format.
    Example: '2026-05-15T14:00:00Z' → '2026-05-15T16:00:00+02:00'
    """
    
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    dt_rome = dt.astimezone(ZoneInfo("Europe/Rome"))
    return dt_rome.isoformat()

def get_random_waiting_time(min_sec: int, max_sec: int) -> float:
    """Return a random waiting time in seconds between min_sec and max_sec."""
    return random.uniform(min_sec, max_sec)

def get_poisson_waiting_time(lam: float) -> float:
    """Return a random waiting time in seconds drawn from an exponential 
    distribution with mean 'lam' (representing a Poisson process)."""
    return random.expovariate(1/lam)