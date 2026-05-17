RTC_TAG = "rtc_event"
from datetime import datetime, timezone
from pathlib import Path

ERROR_COLOR = "\033[91m"


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()

def info(msg: str, *args):
    # If arguments are provided, format the string using the % operator
    if args:
        msg = msg % args
        
    print(f"[{RTC_TAG}][{get_timestamp()}] {msg}", flush=True)

def log_info(msg: str, file_path: Path, *args):
    if args:
        msg = msg % args
        
    timestamped_msg = f"[{RTC_TAG}][{get_timestamp()}] {msg}\n"
    print(timestamped_msg, end="", flush=True)
    file_path.write_text(timestamped_msg, encoding="utf-8", append=True)



def error(msg: str, *args):
    if args:
        msg = msg % args
        
    print(f"{ERROR_COLOR}[{RTC_TAG}][{get_timestamp()}] {msg}\033[0m", flush=True)

def log_error(msg: str, file_path: Path, *args):
    if args:
        msg = msg % args
        
    timestamped_msg = f"{ERROR_COLOR}[{RTC_TAG}][{get_timestamp()}] {msg}\033[0m\n"
    print(timestamped_msg, end="", flush=True)
    file_path.write_text(timestamped_msg, encoding="utf-8", append=True)    