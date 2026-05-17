from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import threading
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class IpcEventServer:
    """Small Unix datagram server used by lab Makefiles to report state changes."""

    def __init__(self, socket_path: Path, events_path: Path) -> None:
        self.socket_path = socket_path
        self.events_path = events_path
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    def __enter__(self) -> "IpcEventServer":
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        self.events_path.write_text("", encoding="utf-8")

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(str(self.socket_path))
        self._sock.settimeout(0.25)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            self._sock.close()
        self.socket_path.unlink(missing_ok=True)

    def load_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []

        events: list[dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _serve(self) -> None:
        assert self._sock is not None
        with self.events_path.open("a", encoding="utf-8") as file_obj:
            while not self._stop_event.is_set():
                try:
                    raw_message = self._sock.recv(65535)
                except TimeoutError:
                    continue
                event = self._parse_event(raw_message)
                if event is None:
                    continue
                file_obj.write(json.dumps(event, sort_keys=True) + "\n")
                file_obj.flush()

    def _parse_event(self, raw_message: bytes) -> dict[str, Any] | None:
        try:
            payload = json.loads(raw_message.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None

        payload.setdefault("ts_utc", utc_now_iso())
        payload["received_utc"] = utc_now_iso()
        return payload
