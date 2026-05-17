from pathlib import Path
import socket
import threading
from typing import Any
import json
from experiments.core import timing
output_dir = "test_output"

class IPCManager:
    def __init__(self, socket_name: str):
        self._ipc_events = []
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._events: list[dict[str, Any]] = []
        self.events_file = Path(output_dir +  "/ipc_events.jsonl")
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        self.events_file.write_text("", encoding="utf-8")
        self.socket_path = Path("/tmp") / socket_name
        self.log_file = Path(output_dir) / "lab.log"

    def _start_ipc_server(self) -> None:
        """Start Unix datagram socket to receive lab events."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.bind(str(self.socket_path))
        self._sock.settimeout(0.25)
        self._stop.clear()
        
        self._thread = threading.Thread(target=self._serve_ipc, daemon=True)
        self._thread.start()
    
    def _stop_ipc_server(self) -> None:
        """Stop IPC server and clean up."""
        self._stop.set()
        
        if self._thread:
            self._thread.join(timeout=2)
        
        if self._sock:
            self._sock.close()
        
        self.socket_path.unlink(missing_ok=True)
    
    def _serve_ipc(self) -> None:
        """Background thread: receive events and append to file."""
        assert self._sock is not None
        
        with self.events_file.open("a", encoding="utf-8") as f:
            while not self._stop.is_set():
                try:
                    raw = self._sock.recv(65535)
                except (TimeoutError, OSError):
                    continue
                
                event = self._parse_event(raw)
                if event:
                    self._events.append(event)
                    f.write(json.dumps(event, sort_keys=True) + "\n")
                    f.flush()
    
    def _parse_event(self, raw: bytes) -> dict[str, Any] | None:
        """Parse incoming JSON event."""
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        
        if not isinstance(event, dict):
            return None
        
        # Add timestamps if missing
        event.setdefault("ts_utc", timing.utc_now_iso())
        event["received_utc"] = timing.utc_now_iso()
        
        return event