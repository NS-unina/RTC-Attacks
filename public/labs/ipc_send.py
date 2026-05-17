#!/usr/bin/env python3
"""IPC event client: send events to Unix socket."""

import json
import os
import socket
import sys


def main() -> int:
    """Send IPC event to Unix socket.
    
    Usage: ipc_send <state> [key=value ...]
    
    Example:
        RTC_IPC_SOCKET=/tmp/rtc.sock ipc_send lab_ready stack=lab_1 scenario=1 instance=1
    """
    if len(sys.argv) < 2:
        return 0
    
    # Socket path from environment variable
    socket_path = os.environ.get("RTC_IPC_SOCKET", "/tmp/rtc.sock")
    if not socket_path:
        return 0
    
    state = sys.argv[1]
    event = {"state": state}
    
    # Parse key=value arguments
    for arg in sys.argv[2:]:
        if "=" not in arg:
            continue
        key, value = arg.split("=", 1)
        event[key] = int(value) if value.isdigit() else value
    
    # Send to socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(json.dumps(event).encode("utf-8"), socket_path)
    except OSError:
        return 1
    finally:
        sock.close()
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
