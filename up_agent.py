"""
up_agent.py
─────────────────────────────────────────────────────────────────────────────
Up-Agent  (Bullish Specialist)
─────────────────────────────────────────────────────────────────────────────
Responsibilities:
  • Manages the LONG perpetual futures leg of a composite trade package
  • Monitors bullish signals exclusively: RSI, MACD, EMA crossovers,
    positive funding, whale accumulation, upward momentum
  • Decides entry refinement (limit vs market), trailing stop adjustments,
    and partial profit taking on the long side
  • Communicates decisions back to the Supervisor via shared TradePackage state
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from config import settings
from exchange_client import (
    fetch_market_snapshot,
    fetch_ohlcv,
    open_long_leg,
    close_leg_market,
)
from models import (
    AgentRole,
    AgentVote,
    LegState,
    LegStatus,
    MarketSnapshot,
    Side,
    SignalStrength,
    TradePackage,
)
from risk_manager import risk_manager


# ─────────────────────────────────────────────────────────────────────────────
# Bullish Technical Signals
# ─────────────────────────────────────────────────────────────────────────────

def _compute_rsi(closes: list, period: int = 14) -> float:
    """Simple RSI calculation without external library dependency."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _ema(closes: list, span: int) -> float:
    """Exponential moving average, last value only."""
    s = pd.Series(closes)
    return float(s.ewm(span=span, adjust=False).mean().iloc[-1])


def _macd_histogram(closes: list) -> float:
    """MACD histogram = MACD line − signal line."""
    fast = pd.Series(closes).ewm(span=12, adjust=False).mean()
    slow = pd.Series(closes).ewm(span=26, adjust=False).mean()
    macd_line = fast - slow
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return float((macd_line - signal).iloc[-1])


def _bullish_signal_score(
    closes: list,
    volumes: list,
    funding_rate: float,
) -> float:
    """
    Aggregate bullish signal score  0.0 – 1.0.
    Each sub-signal contributes equally (5 signals × 0.2 weight).
    """
    score = 0.0

    # 1. RSI oversold/neutral → bullish
    rsi = _compute_rsi(closes)
    if rsi < 35:
        score += 0.20    # oversold — strong bull
    elif rsi < 55:
        score += 0.12    # neutral-bullish
    elif rsi < 70:
        score += 0.06    # mild bull momentum

    # 2. EMA 20 > EMA 50 crossover
    if len(closes) >= 50:
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        if ema20 > ema50:
            score += 0.20

    # 3. MACD histogram positive (bullish divergence)
    macd_h = _macd_histogram(closes)
    if macd_h > 0:
        score += 0.20

    # 4. Negative funding rate → shorts are paying → bullish bias
    if funding_rate < -0.0001:
        score += 0.20
    elif funding_rate < 0:
        score += 0.10

    # 5. Volume surge on up bars (last candle)
    if len(closes) >= 2 and len(volumes) >= 2:
        price_up = closes[-1] > closes[-2]
        vol_surge = volumes[-1] > np.mean(volumes[-20:]) * 1.3
        if price_up and vol_surge:
            score += 0.20

    return min(score, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Up-Agent class
# ─────────────────────────────────────────────────────────────────────────────

class UpAgent:
    """
    Bullish specialist agent.
    Lifecycle: vote() → open_leg() → monitor_loop() → close_leg()
    """

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id: str = agent_id or f"up-{uuid.uuid4().hex[:6]}"
        self.role = AgentRole.UP_AGENT
        self._running = False

    # ─────────────────────────────────────────────────────────────────
    # Step 1: Vote (called by swarm before package is opened)
    # ─────────────────────────────────────────────────────────────────

    async def vote(self, symbol: str) -> AgentVote:
        """
        Analyse bullish signals for `symbol` and return a vote.
        """
        try:
            snapshot = await fetch_market_snapshot(settings.long_exchange_id, symbol)
            bars = await fetch_ohlcv(
                settings.long_exchange_id, symbol, timeframe="1h", limit=100
            )
            closes = [b[4] for b in bars]
            volumes = [b[5] for b in bars]

            bull_score = _bullish_signal_score(closes, volumes, snapshot.funding_rate)

            if bull_score >= 0.75:
                signal = SignalStrength.STRONG_BULL
            elif bull_score >= 0.55:
                signal = SignalStrength.MILD_BULL
            elif bull_score >= 0.40:
                signal = SignalStrength.NEUTRAL
            elif bull_score >= 0.25:
                signal = SignalStrength.MILD_BEAR
            else:
                signal = SignalStrength.STRONG_BEAR

            rsi = _compute_rsi(closes)
            macd_h = _macd_histogram(closes)

            logger.info(
                f"[UpAgent:{self.agent_id}] {symbol} bull_score={bull_score:.2f} "
                f"RSI={rsi:.1f} MACD_hist={macd_h:.4f} funding={snapshot.funding_rate:.5f}"
            )

            return AgentVote(
                agent_id=self.agent_id,
                role=self.role,
                signal=signal,
                confidence=bull_score,
                rationale=(
                    f"RSI={rsi:.1f}, MACD_hist={macd_h:.4f}, "
                    f"funding={snapshot.funding_rate:.5f}, score={bull_score:.2f}"
                ),
            )
        except Exception as e:
            logger.error(f"[UpAgent:{self.agent_id}] vote() error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                role=self.role,
                signal=SignalStrength.NEUTRAL,
                confidence=0.0,
                rationale=f"Error: {e}",
            )

    # ─────────────────────────────────────────────────────────────────
    # Step 2: Open long leg (called by Supervisor after approval)
    # ─────────────────────────────────────────────────────────────────

    async def open_leg(
        self,
        package: TradePackage,
        quantity: float,
        mark_price: float,
    ) -> LegState:
        """
        Instantiate and open the long leg.  Returns the filled LegState.
        """
        leg = LegState(
            package_id=package.package_id,
            side=Side.LONG,
            exchange_id=settings.long_exchange_id,
            symbol=package.symbol,
            quantity=quantity,
            leverage=settings.default_leverage,
            weight=package.consensus.long_weight if package.consensus else 0.5,
        )
        leg = await open_long_leg(leg, mark_price)
        package.long_leg = leg
        logger.info(
            f"[UpAgent:{self.agent_id}] Long leg opened: "
            f"{quantity} {package.symbol} @ {leg.entry_price} "
            f"SL={leg.stop_loss_price} TP={leg.take_profit_price}"
        )
        return leg

    # ─────────────────────────────────────────────────────────────────
    # Step 3: Monitor loop (runs concurrently with DownAgent loop)
    # ─────────────────────────────────────────────────────────────────

    async def monitor_loop(
        self,
        package: TradePackage,
        stop_event: asyncio.Event,
    ) -> None:
        """
        Per-tick monitoring for the long leg.
        Checks trailing stops, updates unrealised PnL, signals
        the Supervisor via `stop_event` if the leg needs to be killed.
        """
        self._running = True
        leg = package.long_leg
        if not leg:
            return

        logger.info(f"[UpAgent:{self.agent_id}] Starting monitor loop for leg {leg.leg_id}")

        while not stop_event.is_set() and leg.status == LegStatus.OPEN:
            try:
                snap: MarketSnapshot = await fetch_market_snapshot(
                    leg.exchange_id, leg.symbol
                )
                leg.current_price = snap.mark_price

                # Update unrealised PnL
                if leg.side == Side.LONG:
                    leg.unrealized_pnl = (
                        (snap.mark_price - leg.entry_price)
                        / leg.entry_price
                        * leg.notional_usdt
                    )

                # Update trailing stop
                leg = risk_manager.update_trailing_stop(leg, snap.mark_price)

                # Check if trailing stop triggered
                if risk_manager.check_trailing_stop_triggered(leg, snap.mark_price):
                    logger.info(
                        f"[UpAgent:{self.agent_id}] Trailing stop hit on long leg "
                        f"{leg.leg_id}. Signalling close."
                    )
                    stop_event.set()
                    break

                # Hard stop-loss check (exchange SL may not always fire in paper mode)
                if snap.mark_price <= leg.stop_loss_price:
                    logger.warning(
                        f"[UpAgent:{self.agent_id}] STOP LOSS hit on long leg: "
                        f"price={snap.mark_price} <= SL={leg.stop_loss_price}"
                    )
                    stop_event.set()
                    break

                # Take-profit check
                if snap.mark_price >= leg.take_profit_price:
                    logger.info(
                        f"[UpAgent:{self.agent_id}] TAKE PROFIT hit on long leg: "
                        f"price={snap.mark_price} >= TP={leg.take_profit_price}"
                    )
                    stop_event.set()
                    break

                package.update_combined_pnl()
                await asyncio.sleep(settings.signal_refresh_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[UpAgent:{self.agent_id}] monitor_loop error: {e}")
                await asyncio.sleep(5)

        self._running = False

    # ─────────────────────────────────────────────────────────────────
    # Step 4: Close leg
    # ─────────────────────────────────────────────────────────────────

    async def close_leg(self, package: TradePackage, reason: str = "") -> None:
        if package.long_leg and package.long_leg.status == LegStatus.OPEN:
            logger.info(
                f"[UpAgent:{self.agent_id}] Closing long leg. Reason: {reason}"
            )
            package.long_leg = await close_leg_market(package.long_leg)

    # ─────────────────────────────────────────────────────────────────
    # Rebalance: adjust position size
    # ─────────────────────────────────────────────────────────────────

    async def rebalance(
        self,
        package: TradePackage,
        new_weight: float,
        mark_price: float,
    ) -> None:
        """
        Adjust the long leg size to match the new target weight.
        Only increases or partial-closes — no full close/reopen.
        """
        leg = package.long_leg
        if not leg or leg.status != LegStatus.OPEN:
            return

        current_notional = leg.notional_usdt
        target_notional = package.risk_budget_usdt * new_weight * settings.default_leverage
        delta = target_notional - current_notional

        if abs(delta) < current_notional * 0.05:
            return  # less than 5% change — skip

        delta_qty = abs(delta) / mark_price

        # Use defense if available (passed by orchestrator in _attach_monitor)
        _defense = getattr(self, '_defense', None)

        if delta > 0:
            # Increase long — add to position (route through defense if active)
            if _defense and _defense.is_active:
                await _defense.defended_place_order(
                    leg.exchange_id, leg.symbol, Side.LONG,
                    round(delta_qty, 6), reduce_only=False, use_stealth=True,
                )
            else:
                from exchange_client import place_market_order
                await place_market_order(
                    leg.exchange_id, leg.symbol, Side.LONG, round(delta_qty, 6)
                )
            leg.quantity += round(delta_qty, 6)
            leg.notional_usdt = target_notional
            leg.weight = new_weight
            logger.info(
                f"[UpAgent:{self.agent_id}] Rebalanced LONG: added {delta_qty:.6f} "
                f"(new weight={new_weight:.2f})"
            )
        else:
            # Reduce long — partial close (route through defense if active)
            if _defense and _defense.is_active:
                await _defense.defended_place_order(
                    leg.exchange_id, leg.symbol, Side.SHORT,
                    round(delta_qty, 6), reduce_only=True,
                )
            else:
                from exchange_client import place_market_order
                await place_market_order(
                    leg.exchange_id, leg.symbol, Side.SHORT, round(delta_qty, 6),
                    reduce_only=True,
                )

            leg.quantity -= round(delta_qty, 6)
            leg.notional_usdt = target_notional
            leg.weight = new_weight
            logger.info(
                f"[UpAgent:{self.agent_id}] Rebalanced LONG: reduced by {delta_qty:.6f} "
                f"(new weight={new_weight:.2f})"
            )
