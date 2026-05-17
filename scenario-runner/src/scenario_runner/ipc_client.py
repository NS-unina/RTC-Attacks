#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a scenario-runner IPC event")
    parser.add_argument("state", help="State name, e.g. lab_start, attack_start, attack_end")
    parser.add_argument("fields", nargs="*", help="Additional key=value fields")
    parser.add_argument("--socket", default=os.environ.get("RTC_IPC_SOCKET", ""))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.socket:
        return 0

    event: dict[str, object] = {"state": args.state}
    for raw_field in args.fields:
        if "=" not in raw_field:
            continue
        key, value = raw_field.split("=", 1)
        event[key] = int(value) if value.isdigit() else value

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(json.dumps(event).encode("utf-8"), args.socket)
    except OSError as exc:
        print(f"scenario-runner IPC send failed: {exc}", file=sys.stderr)
        return 1
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
