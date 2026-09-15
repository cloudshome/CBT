"""
cbt_backend.py
==============
Entrypoint for the compiled / background CBT Python backend server.

Security & Architectural Invariants:
- STRICT LOCAL LOOPBACK BINDING: Binds exclusively to 127.0.0.1 to prevent LAN exposure.
- Automated port allocation fallback if 8000 is occupied.
- Clean shutdown handler for DB connections and real-time streams.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
from pathlib import Path

import uvicorn

REPO_ROOT = Path(__file__).resolve().parent
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PORT = 8000
HOST = "127.0.0.1"


def is_port_available(port: int) -> bool:
    """Checks if a TCP port is free on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except socket.error:
            return False


def find_available_port(start_port: int = DEFAULT_PORT, max_attempts: int = 20) -> int:
    """Finds an available port starting from start_port."""
    for p in range(start_port, start_port + max_attempts):
        if is_port_available(p):
            return p
    raise RuntimeError(f"Could not find an available port in range {start_port}-{start_port + max_attempts}")


def main() -> None:
    # Ensure port is selected
    port_env = os.getenv("CBT_BACKEND_PORT")
    if port_env and port_env.isdigit():
        port = int(port_env)
    else:
        port = DEFAULT_PORT if is_port_available(DEFAULT_PORT) else find_available_port(8001)

    # Inform Electron supervisor via stdout
    print(f"CBT_BACKEND_READY:http://{HOST}:{port}", flush=True)

    # Graceful shutdown handler
    def handle_exit(signum, frame):
        print("CBT Backend shutting down gracefully...", flush=True)
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handle_exit)
        signal.signal(signal.SIGTERM, handle_exit)
    except Exception:
        pass

    # Run Uvicorn strictly on loopback
    uvicorn.run(
        "app:app",
        host=HOST,
        port=port,
        log_level="info",
        access_log=False,
        timeout_keep_alive=65,
    )


if __name__ == "__main__":
    main()
