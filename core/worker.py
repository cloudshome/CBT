"""
Dedicated Background Daemon Worker Process for SKY / CBT.
Decouples heavy background research, walk-forward accumulation, shadow burn-in,
and autonomous trading loops from the authoritative FastAPI web event loop.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from core.autonomous_trader import autonomous_trader
from core.collective.sync_daemon import cluster_sync_daemon
from core.database import db_manager
from core.empirical_accumulator import empirical_accumulator
from core.hf_telemetry_pipeline import hf_telemetry_pipeline
from core.knowledge_os.research_automation_orchestrator import research_automation_orchestrator
from core.mastermind.mastermind_arbiter import mastermind_arbiter
from core.shadow_burn_in_orchestrator import shadow_burn_in_orchestrator
from core.telegram.jobs import job_manager
from core.telegram_bot import telegram_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_quant_sentinel.worker")


async def empirical_accumulator_loop() -> None:
    """Periodically executes chronological walk-forward validations to build sample sizes."""
    while True:
        try:
            await asyncio.to_thread(empirical_accumulator.run_accumulation_cycle)
        except Exception as e:
            logger.debug(f"Empirical accumulator loop error: {e}")
        await asyncio.sleep(300.0)


def flush_wal_checkpoints() -> None:
    """Flushes SQLite WAL files across all databases for clean persistence."""
    logger.info("Executing SQLite WAL flush checkpoints...")
    for db_getter in (
        db_manager.get_market_conn,
        db_manager.get_brain_conn,
        db_manager.get_trading_conn,
        db_manager.get_experiment_conn,
    ):
        try:
            with db_getter() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception as e:
            logger.warning(f"WAL checkpoint note: {e}")


async def run_worker() -> None:
    logger.info("Starting SKY Dedicated Background Daemon Worker...")
    db_manager.init_all_schemas()
    job_manager.reconcile_orphaned_jobs()

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: stop_event.set())

    tasks = [
        asyncio.create_task(empirical_accumulator_loop()),
        asyncio.create_task(telegram_bot.start_polling()),
        asyncio.create_task(telegram_bot.start_continuous_broadcaster(interval_seconds=180)),
        asyncio.create_task(autonomous_trader.start_loop()),
        asyncio.create_task(shadow_burn_in_orchestrator.start_loop()),
        asyncio.create_task(hf_telemetry_pipeline.start_flush_loop()),
        asyncio.create_task(research_automation_orchestrator.start_loop()),
        asyncio.create_task(mastermind_arbiter.start_loop(interval_sec=60.0)),
        asyncio.create_task(cluster_sync_daemon.start()),
    ]

    logger.info(
        "SKY Worker online with 9 background daemons: Empirical Accumulator, Telegram Polling & Broadcaster, "
        "Autonomous Trader, Shadow Burn-In, HF Telemetry Flusher, Research Orchestrator, Mastermind Arbiter, & Cluster Sync."
    )

    try:
        await stop_event.wait()
    finally:
        logger.info("Shutdown signal received. Gracefully stopping daemons...")
        await cluster_sync_daemon.stop()
        shadow_burn_in_orchestrator.stop()
        research_automation_orchestrator.stop()
        hf_telemetry_pipeline.flush_to_sqlite()
        flush_wal_checkpoints()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("SKY Worker shutdown complete.")


def main() -> None:
    try:
        asyncio.run(run_worker())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
