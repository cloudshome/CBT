# cbt_backend.py
# CBT Master FastAPI Engine Supervisor.
# Ensures persistent, continuous uvicorn execution on port 8000 with true subprocess isolation & auto-recovery.

import logging
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cbt.supervisor")


def run_supervisor():
    restart_count = 0
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--timeout-keep-alive",
        "30",
    ]

    while True:
        proc = None
        try:
            logger.info(f"Supervisor: Launching CBT engine (Run #{restart_count + 1}) on 127.0.0.1:8000...")
            proc = subprocess.Popen(cmd)
            exit_code = proc.wait()
            restart_count += 1
            logger.warning(f"Supervisor: Engine exited with code {exit_code}. Auto-restarting in 2s (Restart #{restart_count})...")
            time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Supervisor: KeyboardInterrupt received. Halting engine...")
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            sys.exit(0)
        except Exception as exc:
            restart_count += 1
            logger.error(f"Supervisor error: {exc}. Restarting in 2s...")
            time.sleep(2)


if __name__ == "__main__":
    run_supervisor()


