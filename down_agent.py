"""
down_agent.py
─────────────────────────────────────────────────────────────────────────────
Down-Agent  (Bearish Specialist)
─────────────────────────────────────────────────────────────────────────────
Responsibilities:
  • Manages the SHORT perpetual futures leg of a composite trade package
  • Monitors bearish signals exclusively: RSI overbought, MACD bearish
    crossover, negative funding, bearish order-flow, liquidation cascades,
    high positive funding (longs paying — shorts benefit)
  • Mirrors the UpAgent interface so the Supervisor can manage both uniformly
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
    open_short_leg,
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
# Bearish Technical Signals
# ─────────────────────────────────────────────────────────────────────────────

def _compute_rsi(closes: list, period: int = 14) -> float:
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
    s = pd.Series(closes)
    return float(s.ewm(span=span, adjust=False).mean().iloc[-1])


def _macd_histogram(closes: list) -> float:
    fast = pd.Series(closes).ewm(span=12, adjust=False).mean()
    slow = pd.Series(closes).ewm(span=26, adjust=False).mean()
    macd_line = fast - slow
    signal = macd_line.ewm(span=9, adjust=False).mean()
    return float((macd_line - signal).iloc[-1])


def _bearish_signal_score(
    closes: list,
    volumes: list,
    funding_rate: float,
    open_interest_change_pct: float = 0.0,
) -> float:
    """
    Aggregate bearish signal score  0.0 – 1.0.
    Higher = stronger bearish conviction.
    """
    score = 0.0

    # 1. RSI overbought
    rsi = _compute_rsi(closes)
    if rsi > 70:
        score += 0.20    # overbought — strong bear
    elif rsi > 55:
        score += 0.12    # mildly elevated
    elif rsi > 45:
        score += 0.06

    # 2. EMA 20 < EMA 50 (death cross)
    if len(closes) >= 50:
        ema20 = _ema(closes, 20)
        ema50 = _ema(closes, 50)
        if ema20 < ema50:
            score += 0.20

    # 3. MACD histogram negative (bearish divergence)
    macd_h = _macd_histogram(closes)
    if macd_h < 0:
        score += 0.20

    # 4. High positive funding → longs are paying fees → overextended longs
    if funding_rate > 0.0003:
        score += 0.20
    elif funding_rate > 0.0001:
        score += 0.10

    # 5. Volume surge on down bars (last candle)
    if len(closes) >= 2 and len(volumes) >= 2:
        price_down = closes[-1] < closes[-2]
        vol_surge = volumes[-1] > np.mean(volumes[-20:]) * 1.3
        if price_down and vol_surge:
            score += 0.20

    # Bonus: open interest falling = longs closing → bearish confirmation
    if open_interest_change_pct < -2.0:
        score = min(score + 0.10, 1.0)

    return min(score, 1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Down-Agent class
# ─────────────────────────────────────────────────────────────────────────────

class DownAgent:
    """
    Bearish specialist agent.
    Lifecycle: vote() → open_leg() → monitor_loop() → close_leg()
    """

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id: str = agent_id or f"dn-{uuid.uuid4().hex[:6]}"
        self.role = AgentRole.DOWN_AGENT
        self._running = False

    # ─────────────────────────────────────────────────────────────────
    # Step 1: Vote
    # ─────────────────────────────────────────────────────────────────

    async def vote(self, symbol: str) -> AgentVote:
        try:
            snapshot = await fetch_market_snapshot(settings.short_exchange_id, symbol)
            bars = await fetch_ohlcv(
                settings.short_exchange_id, symbol, timeframe="1h", limit=100
            )
            closes = [b[4] for b in bars]
            volumes = [b[5] for b in bars]

            bear_score = _bearish_signal_score(
                closes, volumes, snapshot.funding_rate
            )

            if bear_score >= 0.75:
                signal = SignalStrength.STRONG_BEAR
            elif bear_score >= 0.55:
                signal = SignalStrength.MILD_BEAR
            elif bear_score >= 0.40:
                signal = SignalStrength.NEUTRAL
            elif bear_score >= 0.25:
                signal = SignalStrength.MILD_BULL
            else:
                signal = SignalStrength.STRONG_BULL

            rsi = _compute_rsi(closes)
            macd_h = _macd_histogram(closes)

            logger.info(
                f"[DownAgent:{self.agent_id}] {symbol} bear_score={bear_score:.2f} "
                f"RSI={rsi:.1f} MACD_hist={macd_h:.4f} funding={snapshot.funding_rate:.5f}"
            )

            return AgentVote(
                agent_id=self.agent_id,
                role=self.role,
                signal=signal,
                confidence=bear_score,
                rationale=(
                    f"RSI={rsi:.1f}, MACD_hist={macd_h:.4f}, "
                    f"funding={snapshot.funding_rate:.5f}, score={bear_score:.2f}"
                ),
            )
        except Exception as e:
            logger.error(f"[DownAgent:{self.agent_id}] vote() error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                role=self.role,
                signal=SignalStrength.NEUTRAL,
                confidence=0.0,
                rationale=f"Error: {e}",
            )

    # ─────────────────────────────────────────────────────────────────
    # Step 2: Open short leg
    # ─────────────────────────────────────────────────────────────────

    async def open_leg(
        self,
        package: TradePackage,
        quantity: float,
        mark_price: float,
    ) -> LegState:
        leg = LegState(
            package_id=package.package_id,
            side=Side.SHORT,
            exchange_id=settings.short_exchange_id,
            symbol=package.symbol,
            quantity=quantity,
            leverage=settings.default_leverage,
            weight=package.consensus.short_weight if package.consensus else 0.5,
        )
        leg = await open_short_leg(leg, mark_price)
        package.short_leg = leg
        logger.info(
            f"[DownAgent:{self.agent_id}] Short leg opened: "
            f"{quantity} {package.symbol} @ {leg.entry_price} "
            f"SL={leg.stop_loss_price} TP={leg.take_profit_price}"
        )
        return leg

    # ─────────────────────────────────────────────────────────────────
    # Step 3: Monitor loop
    # ─────────────────────────────────────────────────────────────────

    async def monitor_loop(
        self,
        package: TradePackage,
        stop_event: asyncio.Event,
    ) -> None:
        self._running = True
        leg = package.short_leg
        if not leg:
            return

        logger.info(f"[DownAgent:{self.agent_id}] Starting monitor loop for leg {leg.leg_id}")

        while not stop_event.is_set() and leg.status == LegStatus.OPEN:
            try:
                snap: MarketSnapshot = await fetch_market_snapshot(
                    leg.exchange_id, leg.symbol
                )
                leg.current_price = snap.mark_price

                # Update unrealised PnL for short
                if leg.side == Side.SHORT:
                    leg.unrealized_pnl = (
                        (leg.entry_price - snap.mark_price)
                        / leg.entry_price
                        * leg.notional_usdt
                    )

                # Update trailing stop (moves down as price falls)
                leg = risk_manager.update_trailing_stop(leg, snap.mark_price)

                # Trailing stop triggered
                if risk_manager.check_trailing_stop_triggered(leg, snap.mark_price):
                    logger.info(
                        f"[DownAgent:{self.agent_id}] Trailing stop hit on short leg. Closing."
                    )
                    stop_event.set()
                    break

                # Hard stop-loss (price moved against short)
                if snap.mark_price >= leg.stop_loss_price:
                    logger.warning(
                        f"[DownAgent:{self.agent_id}] STOP LOSS hit on short leg: "
                        f"price={snap.mark_price} >= SL={leg.stop_loss_price}"
                    )
                    stop_event.set()
                    break

                # Take-profit (price moved in favour of short)
                if snap.mark_price <= leg.take_profit_price:
                    logger.info(
                        f"[DownAgent:{self.agent_id}] TAKE PROFIT hit on short leg: "
                        f"price={snap.mark_price} <= TP={leg.take_profit_price}"
                    )
                    stop_event.set()
                    break

                package.update_combined_pnl()
                await asyncio.sleep(settings.signal_refresh_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DownAgent:{self.agent_id}] monitor_loop error: {e}")
                await asyncio.sleep(5)

        self._running = False

    # ─────────────────────────────────────────────────────────────────
    # Step 4: Close leg
    # ─────────────────────────────────────────────────────────────────

    async def close_leg(self, package: TradePackage, reason: str = "") -> None:
        if package.short_leg and package.short_leg.status == LegStatus.OPEN:
            logger.info(
                f"[DownAgent:{self.agent_id}] Closing short leg. Reason: {reason}"
            )
            package.short_leg = await close_leg_market(package.short_leg)

    # ─────────────────────────────────────────────────────────────────
    # Rebalance: adjust position size
    # ─────────────────────────────────────────────────────────────────

    async def rebalance(
        self,
        package: TradePackage,
        new_weight: float,
        mark_price: float,
    ) -> None:
        leg = package.short_leg
        if not leg or leg.status != LegStatus.OPEN:
            return

        current_notional = leg.notional_usdt
        target_notional = package.risk_budget_usdt * new_weight * settings.default_leverage
        delta = target_notional - current_notional

        if abs(delta) < current_notional * 0.05:
            return

        delta_qty = abs(delta) / mark_price

        # Use defense if available (passed by orchestrator in _attach_monitor)
        _defense = getattr(self, '_defense', None)

        if delta > 0:
            # Increase short — route through defense if swarm is active
            if _defense and _defense.is_active:
                await _defense.defended_place_order(
                    leg.exchange_id, leg.symbol, Side.SHORT,
                    round(delta_qty, 6), reduce_only=False, use_stealth=True,
                )
            else:
                from exchange_client import place_market_order
                await place_market_order(
                    leg.exchange_id, leg.symbol, Side.SHORT, round(delta_qty, 6)
                )
            leg.quantity += round(delta_qty, 6)
            leg.notional_usdt = target_notional
            leg.weight = new_weight
            logger.info(
                f"[DownAgent:{self.agent_id}] Rebalanced SHORT: added {delta_qty:.6f}"
            )
        else:
            # Reduce short (partial cover) — route through defense if active
            if _defense and _defense.is_active:
                await _defense.defended_place_order(
                    leg.exchange_id, leg.symbol, Side.LONG,
                    round(delta_qty, 6), reduce_only=True,
                )
            else:
                from exchange_client import place_market_order
                await place_market_order(
                    leg.exchange_id, leg.symbol, Side.LONG, round(delta_qty, 6),
                    reduce_only=True,
                )
            leg.quantity -= round(delta_qty, 6)
            leg.notional_usdt = target_notional
            leg.weight = new_weight
            logger.info(
                f"[DownAgent:{self.agent_id}] Rebalanced SHORT: reduced by {delta_qty:.6f}"
            )
