from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DiscoverOptions(BaseModel):
    recursive: bool = False
    only_compose: bool = False
    only_container: Optional[str] = None


class StackInfo(BaseModel):
    name: str
    path: Path
    compose_file: Optional[Path] = None
    services: List[str] = Field(default_factory=list)
    dockerfiles: Dict[str, Path] = Field(default_factory=dict)


class BuildTiming(BaseModel):
    container: str
    t_build_sec: float


class DeploymentMetric(BaseModel):
    stack: str
    stack_path: str
    container: str
    t_build_sec: float
    t_startup_sec: float
    t_total_sec: float
    t_ready_sec: float


class ResourceMetric(BaseModel):
    scope: str = "container"
    stack: str
    stack_path: str
    container: str
    sampling_interval_sec: float = 0.0
    baseline_sample_timestamps_sec: List[float] = Field(default_factory=list)
    attack_sample_timestamps_sec: List[float] = Field(default_factory=list)
    cpu_baseline_samples: List[float] = Field(default_factory=list)
    cpu_attack_samples: List[float] = Field(default_factory=list)
    mem_baseline_samples_mb: List[float] = Field(default_factory=list)
    mem_attack_samples_mb: List[float] = Field(default_factory=list)
    disk_io_baseline_samples_bps: List[float] = Field(default_factory=list)
    disk_io_attack_samples_bps: List[float] = Field(default_factory=list)
    cpu_baseline: float
    cpu_attack: float
    cpu_peak: float
    mem_baseline_mb: float
    mem_attack_mb: float
    mem_peak_mb: float
    disk_io_baseline_bps: float = 0.0
    disk_io_attack_bps: float = 0.0
    disk_io_peak_bps: float = 0.0


class NetworkMetric(BaseModel):
    stack: str
    stack_path: str
    source: str
    target: str
    port: Optional[int] = None
    protocol: str = "icmp"
    probe_origin: str = "source_container"
    sampling_interval_sec: float = 0.0
    sample_timestamps_sec: List[float] = Field(default_factory=list)
    rtt_samples_ms: List[float] = Field(default_factory=list)
    packet_loss_samples_pct: List[float] = Field(default_factory=list)
    rtt_avg_ms: float
    rtt_peak_ms: float
    packet_loss_rate: float
