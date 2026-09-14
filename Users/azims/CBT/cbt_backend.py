# cbt_backend.py
# CBT Master FastAPI Engine Supervisor.
# Ensures persistent, continuous uvicorn execution on port 8000 with auto-restart.

import logging
import sys
import time
import traceback
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cbt.supervisor")


def run_server():
    restart_count = 0
    while True:
        try:
            logger.info(f"Launching CBT FastAPI engine (Run #{restart_count + 1}) on 127.0.0.1:8000...")
            config = uvicorn.Config(
                "app:app",
                host="127.0.0.1",
                port=8000,
                log_level="info",
                timeout_keep_alive=30,
            )
            server = uvicorn.Server(config)
            server.run()
            restart_count += 1
            logger.warning(f"Uvicorn server exited. Auto-restarting in 2s (Restart #{restart_count})...")
            time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt, stopping supervisor.")
            sys.exit(0)
        except BaseException as exc:
            restart_count += 1
            logger.error(f"Uvicorn exited with exception: {exc} (Restart #{restart_count})")
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    run_server()

