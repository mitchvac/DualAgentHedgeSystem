"""
risk_manager.py
─────────────────────────────────────────────────────────────────────────────
Centralised risk engine for the Dual-Agent Composite Hedge System.
Responsibilities:
  • Position sizing (Kelly-adjusted, max-risk capped)
  • Daily drawdown circuit-breaker
  • Package-level stop / kill decisions
  • Trailing stop updates
  • Rebalance weight computation

BUG FIX (v2):
  • BUG 2 FIXED: Tuple was declared as return type annotation on
    `should_kill_package` but was only imported INSIDE the function body
    (after the annotation is evaluated at class-definition time in Python
    3.12, which raises NameError).  Tuple is now imported at the top of
    this module alongside all other typing imports.  The redundant
    in-function import has been removed.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from datetime import datetime, date
# BUG 2 FIX: Tuple MUST be imported here at module level — it is referenced
# in the return-type annotation of should_kill_package() which Python
# evaluates when the class body is parsed, not when the method is called.
# The old code had `from typing import Tuple` inside the function body
# AFTER the annotation, causing NameError on import.
from typing import Dict, Optional, Tuple

from loguru import logger

from config import settings
from models import (
    LegState,
    LegStatus,
    PackageStatus,
    RebalanceInstruction,
    Side,
    SwarmConsensus,
    TradePackage,
)


# ─────────────────────────────────────────────────────────────────────────────
# Daily drawdown tracker
# ─────────────────────────────────────────────────────────────────────────────

class DailyDrawdownTracker:
    """
    Thread-safe daily PnL / drawdown monitor.
    Raises CircuitBreakerError when the daily limit is breached.
    """

    def __init__(self) -> None:
        self._day: date = date.today()
        self._start_equity: float = 0.0
        self._current_equity: float = 0.0
        self._halted: bool = False
        self._lock = asyncio.Lock()

    async def set_start_equity(self, equity: float) -> None:
        async with self._lock:
            today = date.today()
            if today != self._day:
                self._day = today
                self._start_equity = equity
                self._current_equity = equity
                self._halted = False
                logger.info(f"[Risk] New trading day. Starting equity={equity:.2f} USDT")
            elif self._start_equity == 0:
                self._start_equity = equity
                self._current_equity = equity

    async def update_equity(self, equity: float) -> None:
        async with self._lock:
            self._current_equity = equity
            drawdown_pct = (
                (self._start_equity - equity) / self._start_equity * 100
                if self._start_equity > 0
                else 0
            )
            if drawdown_pct >= settings.max_daily_drawdown_pct and not self._halted:
                self._halted = True
                logger.critical(
                    f"[Risk] CIRCUIT BREAKER TRIGGERED: "
                    f"Daily drawdown {drawdown_pct:.2f}% >= {settings.max_daily_drawdown_pct}%"
                )

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def daily_drawdown_pct(self) -> float:
        if self._start_equity == 0:
            return 0.0
        return (self._start_equity - self._current_equity) / self._start_equity * 100


# Singleton tracker
daily_tracker = DailyDrawdownTracker()


# ─────────────────────────────────────────────────────────────────────────────
# Position sizing
# ─────────────────────────────────────────────────────────────────────────────

def compute_position_sizes(
    account_equity_usdt: float,
    consensus: SwarmConsensus,
    leverage: int,
) -> Dict[str, float]:
    """
    Returns {"long_qty": float, "short_qty": float, "risk_budget_usdt": float}

    Sizing logic:
    1. Risk budget = account_equity × max_risk_pct
    2. Split budget by consensus long/short weights
    3. Quantity = (budget_for_leg × leverage) / mark_price  (caller fills mark_price separately)
    4. Hard cap at max_risk_pct regardless of Kelly
    """
    if account_equity_usdt <= 0:
        return {"long_qty": 0.0, "short_qty": 0.0, "risk_budget_usdt": 0.0}

    # Kelly fraction based on consensus
    edge = abs(consensus.bull_score - consensus.bear_score)  # 0-1
    kelly_fraction = edge * 0.5                              # half-Kelly

    # Cap to max risk per package
    max_fraction = settings.max_risk_per_package_pct / 100.0
    fraction = min(kelly_fraction, max_fraction)
    if fraction < 0.001:
        fraction = max_fraction  # minimum meaningful trade size

    risk_budget = account_equity_usdt * fraction

    long_budget = risk_budget * consensus.long_weight
    short_budget = risk_budget * consensus.short_weight

    # Notional = budget × leverage
    # Quantity will be resolved in each agent once mark_price is known
    return {
        "long_budget_usdt": long_budget * leverage,
        "short_budget_usdt": short_budget * leverage,
        "risk_budget_usdt": risk_budget,
    }


def qty_from_budget(budget_usdt: float, mark_price: float) -> float:
    """Convert USDT notional budget to base-currency quantity."""
    if mark_price <= 0:
        return 0.0
    qty = budget_usdt / mark_price
    return round(qty, 8)


# ─────────────────────────────────────────────────────────────────────────────
# Package-level checks
# ─────────────────────────────────────────────────────────────────────────────

class RiskManager:
    """
    Central risk gate called by the Supervisor on every tick.
    """

    def __init__(self) -> None:
        self.tracker = daily_tracker

    # ── Pre-trade gate ────────────────────────────────────────────────────

    async def approve_trade(
        self,
        consensus: SwarmConsensus,
        account_equity: float,
        existing_packages: int,
    ) -> bool:
        """
        Returns True only if all pre-trade checks pass.
        """
        if self.tracker.is_halted:
            logger.warning("[Risk] Trade blocked — daily circuit breaker is active")
            return False

        if existing_packages >= 3:
            logger.warning("[Risk] Trade blocked — max 3 concurrent packages")
            return False

        if consensus.consensus_score < settings.min_consensus_score:
            logger.info(
                f"[Risk] Consensus {consensus.consensus_score:.2f} < "
                f"threshold {settings.min_consensus_score}"
            )
            return False

        if consensus.volatility_percentile < settings.min_volatility_percentile:
            logger.info(
                f"[Risk] Volatility percentile {consensus.volatility_percentile:.1f} "
                f"< threshold {settings.min_volatility_percentile}"
            )
            return False

        return True

    # ── Per-tick package monitor ──────────────────────────────────────────

    def should_kill_package(self, pkg: TradePackage) -> Tuple[bool, str]:
        """
        Returns (kill: bool, reason: str).
        Kills the package if combined PnL < max risk budget (hard stop).

        BUG 2 FIX: Tuple is now correctly imported at module level above.
        The old code imported Tuple inside this function body AFTER the
        return annotation, which Python 3.12 evaluated at class parse time
        and raised NameError: name 'Tuple' is not defined.
        """
        if pkg.risk_budget_usdt <= 0:
            return False, ""

        loss_pct = -pkg.combined_pnl / pkg.risk_budget_usdt * 100
        if loss_pct >= 100:
            return True, f"Hard stop: combined loss exceeded risk budget ({loss_pct:.1f}%)"

        # Trailing stop on profit: kill if we've given back > trailing_stop_pct of peak
        if settings.trailing_stop_pct and pkg.peak_combined_pnl > 0:
            drawdown_from_peak = pkg.peak_combined_pnl - pkg.combined_pnl
            drawdown_pct = drawdown_from_peak / pkg.risk_budget_usdt * 100
            if drawdown_pct >= settings.trailing_stop_pct:
                return (
                    True,
                    f"Trailing stop: gave back {drawdown_pct:.1f}% from peak",
                )

        return False, ""

    # ── Rebalance computation ─────────────────────────────────────────────

    def compute_rebalance(
        self,
        pkg: TradePackage,
        current_consensus: SwarmConsensus,
    ) -> Optional[RebalanceInstruction]:
        """
        Decide if legs need to be rebalanced.
        Returns a RebalanceInstruction if a change > 5% is warranted.
        """
        new_long_w = current_consensus.long_weight
        new_short_w = current_consensus.short_weight

        if not pkg.long_leg or not pkg.short_leg:
            return None

        old_long_w = pkg.long_leg.weight
        drift = abs(new_long_w - old_long_w)

        if drift < 0.05:   # less than 5% drift — no action
            return None

        rationale = (
            f"Consensus shifted: bull={current_consensus.bull_score:.2f}, "
            f"bear={current_consensus.bear_score:.2f}. "
            f"Rebalancing from {old_long_w:.2f}/{pkg.short_leg.weight:.2f} "
            f"to {new_long_w:.2f}/{new_short_w:.2f}"
        )
        logger.info(f"[Risk] Rebalance triggered for pkg {pkg.package_id}: {rationale}")

        return RebalanceInstruction(
            package_id=pkg.package_id,
            new_long_weight=new_long_w,
            new_short_weight=new_short_w,
            rationale=rationale,
        )

    # ── Trailing stop update ──────────────────────────────────────────────

    def update_trailing_stop(self, leg: LegState, current_price: float) -> LegState:
        """
        Update trailing stop price as the position moves in our favour.
        Only moves the stop in the favourable direction; never relaxes it.
        """
        if not settings.trailing_stop_pct:
            return leg
        trail_pct = settings.trailing_stop_pct / 100.0

        if leg.side == Side.LONG:
            new_trail = current_price * (1 - trail_pct)
            if leg.trailing_stop_price is None or new_trail > leg.trailing_stop_price:
                leg.trailing_stop_price = new_trail
        else:  # SHORT
            new_trail = current_price * (1 + trail_pct)
            if leg.trailing_stop_price is None or new_trail < leg.trailing_stop_price:
                leg.trailing_stop_price = new_trail

        return leg

    def check_trailing_stop_triggered(
        self, leg: LegState, current_price: float
    ) -> bool:
        """Returns True if the trailing stop price has been breached."""
        if leg.trailing_stop_price is None:
            return False
        if leg.side == Side.LONG and current_price <= leg.trailing_stop_price:
            logger.info(
                f"[Risk] Trailing stop triggered on LONG leg {leg.leg_id}: "
                f"price={current_price} <= trail={leg.trailing_stop_price:.2f}"
            )
            return True
        if leg.side == Side.SHORT and current_price >= leg.trailing_stop_price:
            logger.info(
                f"[Risk] Trailing stop triggered on SHORT leg {leg.leg_id}: "
                f"price={current_price} >= trail={leg.trailing_stop_price:.2f}"
            )
            return True
        return False


# Singleton
risk_manager = RiskManager()
