"""
backtest.py
─────────────────────────────────────────────────────────────────────────────
Paper-trading / Backtesting entry point.

Two modes:
  1. paper  — Run the live system with PAPER_TRADING=true (no real orders)
  2. backtest — Replay historical OHLCV data through the signal engine
               and simulate composite trade outcomes

Usage:
  python backtest.py --mode paper
  python backtest.py --mode backtest --symbol BTC/USDT:USDT --days 30
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List

import pandas as pd
import numpy as np
from loguru import logger

# Force paper trading before any config is imported
os.environ["PAPER_TRADING"] = "true"

from config import settings
from exchange_client import fetch_ohlcv
from models import (
    LegStatus,
    PackageStatus,
    Side,
    SwarmConsensus,
    TradePackage,
    LegState,
)
from risk_manager import compute_position_sizes, qty_from_budget, risk_manager
from up_agent import _bullish_signal_score
from down_agent import _bearish_signal_score


# ─────────────────────────────────────────────────────────────────────────────
# Back-test engine
# ─────────────────────────────────────────────────────────────────────────────

class BacktestResult:
    def __init__(self) -> None:
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.start_equity: float = 10_000.0
        self.final_equity: float = 10_000.0

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity - self.start_equity) / self.start_equity * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return wins / len(self.trades) * 100

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        curve = np.array(self.equity_curve)
        peak = np.maximum.accumulate(curve)
        dd = (curve - peak) / peak * 100
        return float(np.min(dd))

    def print_summary(self) -> None:
        print("\n" + "=" * 60)
        print("  BACKTEST RESULTS")
        print("=" * 60)
        print(f"  Trades executed  : {len(self.trades)}")
        print(f"  Win rate         : {self.win_rate:.1f}%")
        print(f"  Total return     : {self.total_return_pct:.2f}%")
        print(f"  Max drawdown     : {self.max_drawdown_pct:.2f}%")
        print(f"  Start equity     : ${self.start_equity:,.2f}")
        print(f"  Final equity     : ${self.final_equity:,.2f}")
        print("=" * 60)


class HedgeBacktester:
    """
    Vectorised walk-forward backtest for the composite hedge system.
    Uses actual OHLCV data fetched from CCXT (requires internet).
    """

    def __init__(
        self,
        symbol: str,
        start_days_ago: int = 30,
        initial_equity: float = 10_000.0,
        window: int = 100,           # candles needed for signal computation
        step: int = 24,              # evaluate every N candles (1 = every candle)
    ) -> None:
        self.symbol = symbol
        self.start_days_ago = start_days_ago
        self.initial_equity = initial_equity
        self.window = window
        self.step = step

    async def run(self) -> BacktestResult:
        result = BacktestResult()
        result.start_equity = self.initial_equity
        equity = self.initial_equity

        logger.info(
            f"[Backtest] Fetching {self.start_days_ago * 24} hourly bars for {self.symbol}"
        )
        bars = await fetch_ohlcv(
            settings.long_exchange_id,
            self.symbol,
            timeframe="1h",
            limit=self.start_days_ago * 24,
        )

        if len(bars) < self.window + self.step:
            logger.error("[Backtest] Not enough data")
            return result

        timestamps = [b[0] for b in bars]
        opens   = [b[1] for b in bars]
        highs   = [b[2] for b in bars]
        lows    = [b[3] for b in bars]
        closes  = [b[4] for b in bars]
        volumes = [b[5] for b in bars]

        result.equity_curve.append(equity)

        for i in range(self.window, len(bars) - self.step, self.step):
            window_closes  = closes[i - self.window : i]
            window_volumes = volumes[i - self.window : i]

            # Simulate funding rate (use historical avg)
            simulated_funding = np.random.choice([-0.0001, 0.0001, 0.0002, -0.0002, 0.0])

            # Score both sides
            bull_score = _bullish_signal_score(window_closes, window_volumes, simulated_funding)
            bear_score = _bearish_signal_score(window_closes, window_volumes, simulated_funding)

            # Determine volatility percentile of the window
            rets = np.diff(np.log(window_closes))
            rv = np.std(rets) * np.sqrt(24 * 365) * 100
            all_rv = [np.std(np.diff(np.log(closes[j:j+self.window]))) for j in range(0, i - self.window, 24)]
            vol_pct = float(np.searchsorted(sorted(all_rv), rv) / max(len(all_rv), 1) * 100) if all_rv else 50.0

            # Simplified consensus check
            combined_score = (bull_score + bear_score) / 2.0
            if combined_score < 0.50 or vol_pct < settings.min_volatility_percentile:
                result.equity_curve.append(equity)
                continue   # skip — no trade this bar

            # Determine leg weights
            total_s = bull_score + bear_score
            lw = bull_score / total_s
            sw = bear_score / total_s

            # Position sizing
            risk_budget = equity * (settings.max_risk_per_package_pct / 100.0)
            entry_price = closes[i]

            long_notional  = risk_budget * lw * settings.default_leverage
            short_notional = risk_budget * sw * settings.default_leverage
            long_qty  = long_notional  / entry_price
            short_qty = short_notional / entry_price

            # Simulate trade outcome over the next `step` candles
            future_closes = closes[i : i + self.step]
            exit_price = future_closes[-1]

            # Check if SL/TP hit intra-window
            long_sl   = entry_price * (1 - settings.stop_loss_pct / 100)
            long_tp   = entry_price * (1 + settings.take_profit_pct / 100)
            short_sl  = entry_price * (1 + settings.stop_loss_pct / 100)
            short_tp  = entry_price * (1 - settings.take_profit_pct / 100)

            long_exit = exit_price
            short_exit = exit_price
            for fc in future_closes:
                if fc <= long_sl:   long_exit = long_sl;  break
                if fc >= long_tp:   long_exit = long_tp;  break
            for fc in future_closes:
                if fc >= short_sl:  short_exit = short_sl; break
                if fc <= short_tp:  short_exit = short_tp; break

            long_pnl  = (long_exit  - entry_price) / entry_price * long_notional
            short_pnl = (entry_price - short_exit) / entry_price * short_notional
            total_pnl = long_pnl + short_pnl

            equity += total_pnl

            trade_record = {
                "timestamp": datetime.utcfromtimestamp(timestamps[i] / 1000).isoformat(),
                "symbol": self.symbol,
                "entry_price": entry_price,
                "exit_price_long": long_exit,
                "exit_price_short": short_exit,
                "long_pnl": round(long_pnl, 4),
                "short_pnl": round(short_pnl, 4),
                "pnl": round(total_pnl, 4),
                "equity_after": round(equity, 2),
                "long_weight": round(lw, 3),
                "short_weight": round(sw, 3),
                "vol_pct": round(vol_pct, 1),
            }
            result.trades.append(trade_record)
            result.equity_curve.append(equity)

            logger.info(
                f"[Backtest] {trade_record['timestamp']} | "
                f"entry={entry_price:.2f} | "
                f"L_pnl={long_pnl:.2f} S_pnl={short_pnl:.2f} "
                f"total={total_pnl:.2f} | equity={equity:.2f}"
            )

        result.final_equity = equity
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Paper-trading mode (live run, no real orders)
# ─────────────────────────────────────────────────────────────────────────────

async def run_paper() -> None:
    logger.info("[Paper] Starting paper-trading mode")
    from orchestrator import Orchestrator
    orch = Orchestrator()
    try:
        await orch.start()
    except KeyboardInterrupt:
        logger.info("[Paper] Interrupted by user")
    finally:
        await orch.stop()


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dual-Agent Composite Hedge — Backtest / Paper mode"
    )
    parser.add_argument(
        "--mode", choices=["paper", "backtest"], default="paper",
        help="paper: live paper-trading; backtest: historical replay"
    )
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="Symbol to backtest")
    parser.add_argument("--days", type=int, default=30, help="Days of history to backtest")
    parser.add_argument("--equity", type=float, default=10_000.0, help="Starting equity in USDT")
    args = parser.parse_args()

    # Logging setup
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    logger.add("data/system.log", rotation="50 MB", retention="14 days", level="DEBUG")

    if args.mode == "paper":
        asyncio.run(run_paper())
    else:
        async def _bt():
            tester = HedgeBacktester(
                symbol=args.symbol,
                start_days_ago=args.days,
                initial_equity=args.equity,
            )
            result = await tester.run()
            result.print_summary()

            # Save trades to CSV
            if result.trades:
                df = pd.DataFrame(result.trades)
                out_path = f"data/backtest_{args.symbol.replace('/', '_')}_{args.days}d.csv"
                df.to_csv(out_path, index=False)
                logger.info(f"[Backtest] Results saved to {out_path}")

        asyncio.run(_bt())


if __name__ == "__main__":
    main()
