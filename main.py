"""
main.py
─────────────────────────────────────────────────────────────────────────────
System entry point — starts the live orchestrator.
For paper-trading / backtest, use backtest.py instead.

Usage:
  python main.py                    # live mode (reads PAPER_TRADING from .env)
  python main.py --paper            # force paper-trading mode
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


async def _run() -> None:
    from orchestrator import Orchestrator

    orch = Orchestrator()
    logger.info("━" * 60)
    logger.info("  Dual-Agent Composite Hedge Trading System")
    logger.info("━" * 60)

    try:
        await orch.start()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        await orch.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hedge Trading System")
    parser.add_argument("--paper", action="store_true", help="Force paper-trading mode")
    args = parser.parse_args()

    if args.paper:
        os.environ["PAPER_TRADING"] = "true"

    setup_logging()

    # Use uvloop on Linux/macOS for better async perf
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop event loop")
    except ImportError:
        pass

    asyncio.run(_run())


if __name__ == "__main__":
    main()
