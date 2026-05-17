"""PCAP capture store adapter.

Responsibility: locate and read capture artefacts written by Suricata's
continuous capture mode. Abstracts the ``captures/`` directory layout from
the experiment orchestrators.
"""

from __future__ import annotations

from pathlib import Path


class CaptureStore:
    """Reads capture artefacts from the ``<repo_root>/captures/`` directory.

    The directory layout is:
        captures/
            last_root.txt          ← relative path to the most recent capture
            <timestamp>/
                pcap/
                suricata/
                logs/
                meta/
    """

    def __init__(self, repo_root: Path) -> None:
        self._captures_dir = repo_root / "captures"

    def latest_capture_root(self) -> Path:
        """Return the absolute path to the most recent capture directory."""
        marker = self._captures_dir / "last_root.txt"
        if not marker.exists():
            raise FileNotFoundError(f"Missing capture marker: {marker}")
        relative = marker.read_text(encoding="utf-8").strip()
        if not relative:
            raise ValueError("captures/last_root.txt is empty")
        return (self._captures_dir.parent / relative).resolve()

    def latest_pcap(self) -> Path:
        """Return the first PCAP file found in the most recent capture."""
        capture_root = self.latest_capture_root()
        pcap_dir = capture_root / "pcap"
        pcaps = sorted(pcap_dir.glob("*.pcap"))
        if not pcaps:
            raise FileNotFoundError(f"No PCAP files found in: {pcap_dir}")
        return pcaps[0]

    def pcap_files(self, capture_root: Path | None = None) -> list[Path]:
        """Return all PCAP files for a given capture root (defaults to latest)."""
        root = capture_root or self.latest_capture_root()
        return sorted((root / "pcap").glob("*.pcap"))
