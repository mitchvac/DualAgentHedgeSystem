"""
main_fullstack.py
─────────────────────────────────────────────────────────────────────────────
Unified entry point — runs the trading engine, arbitrage module, AND
FastAPI server in the same asyncio event loop.

Usage:
  python main_fullstack.py [--paper]
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from loguru import logger


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=os.getenv("LOG_LEVEL", "INFO"),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    logger.add(
        "data/system.log",
        rotation="50 MB",
        retention="30 days",
        level="DEBUG",
        enqueue=True,
    )


async def _run_engine() -> None:
    """Start the trading orchestrator."""
    from orchestrator import Orchestrator

    orch = Orchestrator()
    logger.info("━" * 60)
    logger.info("  Dual-Agent Composite Hedge Trading System")
    logger.info("  Full-Stack Mode (Engine + Arb + API)")
    logger.info("━" * 60)

    try:
        await orch.start()
    except asyncio.CancelledError:
        logger.info("Engine task cancelled")
    except Exception as e:
        logger.critical(f"Fatal engine error: {e}", exc_info=True)
    finally:
        await orch.stop()


async def _run_arbitrage() -> None:
    """Start the arbitrage scanner."""
    from arbitrage_module import ArbitrageModule

    arb = ArbitrageModule()
    try:
        await arb.start()
        # Keep alive until cancelled
        while arb.is_running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Arbitrage task cancelled")
    finally:
        await arb.stop()


async def _run_api(host: str = "0.0.0.0", port: int = 3003) -> None:
    """Start the Uvicorn server with the FastAPI app."""
    import uvicorn
    from app_fullstack import app

    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    await server.serve()


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="HedgeSwarm Full-Stack + Arbitrage")
    parser.add_argument("--paper", action="store_true", help="Force paper-trading mode")
    parser.add_argument("--api-host", default="0.0.0.0", help="API bind host")
    parser.add_argument("--api-port", type=int, default=3003, help="API bind port")
    parser.add_argument("--no-arb", action="store_true", help="Disable arbitrage module")
    args = parser.parse_args()

    if args.paper:
        os.environ["PAPER_TRADING"] = "true"

    setup_logging()

    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop event loop")
    except ImportError:
        pass

    tasks = [
        asyncio.create_task(_run_engine(), name="engine"),
        asyncio.create_task(_run_api(host=args.api_host, port=args.api_port), name="api"),
    ]

    if not args.no_arb:
        tasks.append(asyncio.create_task(_run_arbitrage(), name="arbitrage"))
        logger.info("[FullStack] Arbitrage module ENABLED (use --no-arb to disable)")
    else:
        logger.info("[FullStack] Arbitrage module DISABLED")

    logger.info("[FullStack] Starting engine + API + arbitrage concurrently")
    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")


if __name__ == "__main__":
    main()
