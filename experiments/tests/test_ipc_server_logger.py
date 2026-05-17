from experiments.core.ipc_manager import IPCManager
import time


if __name__ == "__main__":
    ipc_manager = IPCManager("rtc.sock")
    ipc_manager._start_ipc_server()

    print(f"IPC server started. Listening for events. Output file: {ipc_manager.events_file}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping IPC server...")
        ipc_manager._stop_ipc_server()
        print("IPC server stopped.")

