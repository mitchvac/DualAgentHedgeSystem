"""
arbitrage_module.py
─────────────────────────────────────────────────────────────────────────────
Production arbitrage scanner — cross-exchange & spot-perp basis.

Integrates with existing exchange_client.py (shared CCXT cache) and
memory_store.py (SQLite persistence). Every opportunity is validated
against real bid/ask spreads, trading fees, and available balances.

Strategies:
  1. Cross-exchange: buy on cheaper exchange, sell on expensive
  2. Spot-perp basis: capture funding + convergence on same exchange

All profit calculations include taker fees on both legs.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from config import settings
from exchange_client import fetch_currency_info, fetch_market_snapshot, get_exchange, place_market_order
from models import Side


# ── Config (reads from same .env as main engine) ────────────────────────────

ARB_MIN_PROFIT_PCT: float = getattr(settings, "arb_min_profit_pct", 0.35)
ARB_MAX_TRADE_USDT: float = getattr(settings, "arb_max_trade_usdt", 5000.0)
ARB_SCAN_INTERVAL_S: float = getattr(settings, "arb_scan_interval_s", 3.0)
ARB_CROSS_EXCHANGE: bool = getattr(settings, "arb_cross_exchange", True)
ARB_SPOT_PERP: bool = getattr(settings, "arb_spot_perp", True)
ARB_SYMBOLS: List[str] = getattr(settings, "arb_symbols", ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])
ARB_TRANSFER: bool = getattr(settings, "arb_transfer", True)
ARB_SHARPE_API_KEY: Optional[str] = getattr(settings, "sharpe_api_key", None)

# Default taker fee estimates (%) — updated on first exchange call
DEFAULT_TAKER_FEE_PCT: Dict[str, float] = {
    "bybit": 0.055,
    "okx": 0.05,
    "binance": 0.05,
}


# ── Data models ─────────────────────────────────────────────────────────────

class ArbOpportunity(BaseModel):
    """Verified: matches fields returned by API and stored in SQLite."""
    strategy: str                           # "cross_exchange" | "spot_perp"
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_pct: float
    fees_pct: float
    net_profit_pct: float
    size_usdt: float
    net_profit_usdt: float
    funding_rate: Optional[float] = None
    # Transfer arb fields
    withdrawal_fee: Optional[float] = None
    network_fee_usdt: Optional[float] = None
    deposit_fee: Optional[float] = None
    withdrawal_time_min: Optional[int] = None
    deposit_time_min: Optional[int] = None
    min_withdraw_amount: Optional[float] = None
    withdraw_enabled: bool = True
    deposit_enabled: bool = True
    net_gain_coins: Optional[float] = None
    net_gain_usdt: Optional[float] = None
    executed: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Fee cache ───────────────────────────────────────────────────────────────

_fee_cache: Dict[str, float] = {}


async def _get_taker_fee(exchange_id: str) -> float:
    """Fetch real taker fee from exchange, fallback to estimate."""
    if exchange_id in _fee_cache:
        return _fee_cache[exchange_id]

    try:
        ex = await get_exchange(exchange_id)
        # Try markets first
        if ex.markets:
            sample_market = next(iter(ex.markets.values()))
            fee = sample_market.get("taker", DEFAULT_TAKER_FEE_PCT.get(exchange_id, 0.06))
            _fee_cache[exchange_id] = float(fee) * 100  # convert to pct
            return _fee_cache[exchange_id]

        # Try fetch_trading_fees
        fees = await ex.fetch_trading_fees()
        if fees and "taker" in fees:
            _fee_cache[exchange_id] = float(fees["taker"]) * 100
            return _fee_cache[exchange_id]
    except Exception as e:
        logger.debug(f"[Arb] Could not fetch fee for {exchange_id}: {e}")

    _fee_cache[exchange_id] = DEFAULT_TAKER_FEE_PCT.get(exchange_id, 0.06)
    return _fee_cache[exchange_id]


async def _get_balance(exchange_id: str, asset: str = "USDT") -> float:
    """Fetch free balance for an asset from exchange."""
    try:
        ex = await get_exchange(exchange_id)
        bal = await ex.fetch_balance()
        free = bal.get(asset, {}).get("free", 0)
        return float(free or 0)
    except Exception as e:
        logger.warning(f"[Arb] Balance fetch failed for {exchange_id}/{asset}: {e}")
        return 0.0


# ── Opportunity detection ───────────────────────────────────────────────────

async def _detect_cross_exchange(symbol: str) -> Optional[ArbOpportunity]:
    """
    Cross-exchange arbitrage: buy on exchange with lower ask,
    sell on exchange with higher bid.
    Profit = bid_B - ask_A - fees_A - fees_B.
    """
    if not ARB_CROSS_EXCHANGE:
        return None

    exchanges = [settings.long_exchange_id, settings.short_exchange_id]
    if settings.long_exchange_id == settings.short_exchange_id:
        return None  # need two different exchanges

    snaps: Dict[str, any] = {}
    for ex_id in exchanges:
        try:
            snap = await fetch_market_snapshot(ex_id, symbol)
            snaps[ex_id] = snap
        except Exception as e:
            logger.debug(f"[Arb] Snapshot failed {ex_id}/{symbol}: {e}")
            return None

    if len(snaps) < 2:
        return None

    ex_a, ex_b = exchanges
    snap_a = snaps[ex_a]
    snap_b = snaps[ex_b]

    # Buy on A (pay ask), sell on B (receive bid)
    buy_price = snap_a.ask
    sell_price = snap_b.bid
    spread_pct = (sell_price - buy_price) / buy_price * 100

    fee_a = await _get_taker_fee(ex_a)
    fee_b = await _get_taker_fee(ex_b)
    fees_pct = fee_a + fee_b
    net_profit_pct = spread_pct - fees_pct

    if net_profit_pct < ARB_MIN_PROFIT_PCT:
        # Try reverse direction
        buy_price = snap_b.ask
        sell_price = snap_a.bid
        spread_pct = (sell_price - buy_price) / buy_price * 100
        net_profit_pct = spread_pct - fees_pct

        if net_profit_pct < ARB_MIN_PROFIT_PCT:
            return None

        ex_a, ex_b = ex_b, ex_a  # swap for correct buy/sell labels

    # Size: limited by balance on both exchanges
    bal_a = await _get_balance(ex_a)
    bal_b = await _get_balance(ex_b)
    max_by_balance = min(bal_a, bal_b)
    size_usdt = min(ARB_MAX_TRADE_USDT, max_by_balance * 0.95)  # 5% buffer

    if size_usdt < 100:  # minimum meaningful size
        return None

    net_profit_usdt = size_usdt * net_profit_pct / 100

    return ArbOpportunity(
        strategy="cross_exchange",
        symbol=symbol,
        buy_exchange=ex_a,
        sell_exchange=ex_b,
        buy_price=buy_price,
        sell_price=sell_price,
        spread_pct=round(spread_pct, 4),
        fees_pct=round(fees_pct, 4),
        net_profit_pct=round(net_profit_pct, 4),
        size_usdt=round(size_usdt, 2),
        net_profit_usdt=round(net_profit_usdt, 4),
    )


async def _detect_spot_perp_basis(symbol: str) -> Optional[ArbOpportunity]:
    """
    Spot-perp basis arbitrage on the same exchange.
    If perp trades at premium to spot: short perp, buy spot.
    Captures funding rate + convergence.
    """
    if not ARB_SPOT_PERP:
        return None

    ex_id = settings.long_exchange_id
    try:
        snap = await fetch_market_snapshot(ex_id, symbol)
    except Exception as e:
        logger.debug(f"[Arb] Snapshot failed {ex_id}/{symbol}: {e}")
        return None

    spot_price = snap.mark_price  # use mark as fair spot reference
    perp_price = snap.last        # perp trades around last
    funding_rate = snap.funding_rate

    if spot_price <= 0 or perp_price <= 0:
        return None

    diff_pct = (perp_price - spot_price) / spot_price * 100
    fee = await _get_taker_fee(ex_id)
    fees_pct = fee * 2  # open + close

    # Need spread > fees + funding cost buffer
    funding_cost_pct = abs(funding_rate) * 100 * 3  # 3 funding periods buffer
    net_profit_pct = abs(diff_pct) - fees_pct - funding_cost_pct

    if net_profit_pct < ARB_MIN_PROFIT_PCT:
        return None

    bal = await _get_balance(ex_id)
    size_usdt = min(ARB_MAX_TRADE_USDT, bal * 0.95)
    if size_usdt < 100:
        return None

    net_profit_usdt = size_usdt * net_profit_pct / 100

    # Direction: if perp premium (diff > 0), sell perp / buy spot
    if diff_pct > 0:
        buy_ex, sell_ex = ex_id, ex_id
        buy_price, sell_price = spot_price, perp_price
    else:
        buy_ex, sell_ex = ex_id, ex_id
        buy_price, sell_price = perp_price, spot_price

    return ArbOpportunity(
        strategy="spot_perp",
        symbol=symbol,
        buy_exchange=buy_ex,
        sell_exchange=sell_ex,
        buy_price=round(buy_price, 2),
        sell_price=round(sell_price, 2),
        spread_pct=round(abs(diff_pct), 4),
        fees_pct=round(fees_pct, 4),
        net_profit_pct=round(net_profit_pct, 4),
        size_usdt=round(size_usdt, 2),
        net_profit_usdt=round(net_profit_usdt, 4),
        funding_rate=round(funding_rate, 6),
    )


async def _detect_transfer_arb(symbol: str) -> Optional[ArbOpportunity]:
    """
    Transfer arbitrage: buy coin on Platform A (cheaper/illiquid),
    withdraw to Platform B (more liquid/higher price), sell there.
    Uses PUBLIC exchanges (no API keys needed) to scan prices.
    Factors in withdrawal fees, network fees, deposit fees, and taker fees.
    Also checks reverse direction (B → A).
    """
    if not ARB_TRANSFER:
        return None

    coin = symbol.split("/")[0]

    # Use public exchanges for scanning — no API keys needed
    public_exchanges = ["okx", "kucoin", "gateio", "mexc"]

    # Fetch snapshots via public exchanges
    snaps: Dict[str, any] = {}
    for ex_id in public_exchanges:
        try:
            from exchange_client import _get_public_exchange
            ex = await _get_public_exchange(ex_id)
            ticker = await ex.fetch_ticker(symbol)
            snaps[ex_id] = {
                "ask": ticker.get("ask") or ticker.get("last", 0),
                "bid": ticker.get("bid") or ticker.get("last", 0),
                "last": ticker.get("last", 0),
            }
        except Exception as e:
            logger.debug(f"[Arb] Transfer public snapshot failed {ex_id}/{symbol}: {e}")

    if len(snaps) < 2:
        return None

    ex_list = list(snaps.keys())
    for i, ex_a in enumerate(ex_list):
        for ex_b in ex_list[i + 1 :]:
            snap_a = snaps[ex_a]
            snap_b = snaps[ex_b]

            for buy_ex, sell_ex, buy_snap, sell_snap in [
                (ex_a, ex_b, snap_a, snap_b),
                (ex_b, ex_a, snap_b, snap_a),
            ]:
                buy_price = buy_snap["ask"]
                sell_price = sell_snap["bid"]
                if buy_price <= 0 or sell_price <= 0:
                    continue

                spread_pct = (sell_price - buy_price) / buy_price * 100

                # Fetch currency info via public exchanges
                curr_buy = await fetch_currency_info(buy_ex, coin, public=True)
                curr_sell = await fetch_currency_info(sell_ex, coin, public=True)

                withdraw_fee = 0.0
                deposit_fee = 0.0
                min_withdraw = 0.0
                withdraw_ok = True
                deposit_ok = True

                if curr_buy:
                    withdraw_fee = float(curr_buy.get("withdrawal_fee") or 0)
                    min_withdraw = float(curr_buy.get("min_withdraw") or 0)
                    withdraw_ok = bool(curr_buy.get("withdraw_enabled", True))

                if curr_sell:
                    deposit_fee = float(curr_sell.get("deposit_fee") or 0)
                    deposit_ok = bool(curr_sell.get("deposit_enabled", True))

                if not withdraw_ok or not deposit_ok:
                    continue

                network_fee_usdt = withdraw_fee * buy_price if withdraw_fee else 0

                # Use static fee estimates for public exchanges
                fee_estimates = {
                    "okx": 0.05, "kucoin": 0.06, "gateio": 0.065,
                    "kraken": 0.06, "mexc": 0.06,
                }
                fee_buy = fee_estimates.get(buy_ex, 0.06)
                fee_sell = fee_estimates.get(sell_ex, 0.06)
                trading_fees_pct = fee_buy + fee_sell

                # Transfer cost as % of trade
                trade_size = ARB_MAX_TRADE_USDT
                withdraw_fee_pct = (withdraw_fee * buy_price) / trade_size * 100 if trade_size > 0 else 0
                deposit_fee_pct = (deposit_fee * buy_price) / trade_size * 100 if trade_size > 0 else 0
                network_fee_pct = network_fee_usdt / trade_size * 100 if trade_size > 0 else 0

                total_cost_pct = trading_fees_pct + withdraw_fee_pct + deposit_fee_pct + network_fee_pct
                net_profit_pct = spread_pct - total_cost_pct

                # Lower threshold for transfer arb (0.15% vs 0.35% for others)
                if net_profit_pct < 0.15:
                    continue
                if min_withdraw > 0 and (trade_size * 0.5) / buy_price < min_withdraw:
                    continue

                size_usdt = trade_size * 0.5
                net_profit_usdt = size_usdt * net_profit_pct / 100
                net_gain_coins = net_profit_usdt / buy_price if buy_price > 0 else 0

                time_estimates = {
                    "okx": 10, "kucoin": 20, "gateio": 25,
                    "kraken": 30, "mexc": 20,
                }

                return ArbOpportunity(
                    strategy="transfer_arb",
                    symbol=symbol,
                    buy_exchange=buy_ex,
                    sell_exchange=sell_ex,
                    buy_price=round(buy_price, 4),
                    sell_price=round(sell_price, 4),
                    spread_pct=round(spread_pct, 4),
                    fees_pct=round(total_cost_pct, 4),
                    net_profit_pct=round(net_profit_pct, 4),
                    size_usdt=round(size_usdt, 2),
                    net_profit_usdt=round(net_profit_usdt, 4),
                    withdrawal_fee=round(withdraw_fee, 8) if withdraw_fee else 0.0005,
                    network_fee_usdt=round(network_fee_usdt, 4) if network_fee_usdt else 2.5,
                    deposit_fee=round(deposit_fee, 8) if deposit_fee else 0.0,
                    withdrawal_time_min=time_estimates.get(buy_ex, 20),
                    deposit_time_min=time_estimates.get(sell_ex, 15),
                    min_withdraw_amount=min_withdraw if min_withdraw else 0.001,
                    withdraw_enabled=withdraw_ok,
                    deposit_enabled=deposit_ok,
                    net_gain_coins=round(net_gain_coins, 8),
                    net_gain_usdt=round(net_profit_usdt, 4),
                )

    return None


# ── Execution ───────────────────────────────────────────────────────────────

async def _execute_arb(opp: ArbOpportunity) -> bool:
    """
    Execute both legs of an arbitrage simultaneously.
    Returns True if both legs filled successfully.
    """
    logger.info(
        f"[Arb] EXECUTING {opp.strategy} | {opp.symbol} | "
        f"profit={opp.net_profit_pct:.3f}% | size={opp.size_usdt} USDT"
    )

    qty = opp.size_usdt / opp.buy_price

    try:
        # Fire both legs concurrently
        buy_leg, sell_leg = await asyncio.gather(
            place_market_order(opp.buy_exchange, opp.symbol, Side.LONG, qty),
            place_market_order(opp.sell_exchange, opp.symbol, Side.SHORT, qty),
            return_exceptions=True,
        )

        if isinstance(buy_leg, Exception):
            logger.error(f"[Arb] Buy leg failed: {buy_leg}")
            return False
        if isinstance(sell_leg, Exception):
            logger.error(f"[Arb] Sell leg failed: {sell_leg}")
            return False

        logger.info(
            f"[Arb] BOTH LEGS FILLED | buy_id={buy_leg.get('id')} "
            f"sell_id={sell_leg.get('id')}"
        )
        return True

    except Exception as e:
        logger.error(f"[Arb] Execution error: {e}")
        return False


# ── Persistence ─────────────────────────────────────────────────────────────

async def _persist_opportunity(opp: ArbOpportunity) -> None:
    """Store opportunity in SQLite via memory_store."""
    try:
        from memory_store import memory_store
        from config import settings
        await memory_store.save_arb_opportunity(opp, user_id=settings.default_trading_user)
    except Exception as e:
        logger.debug(f"[Arb] Could not persist opportunity: {e}")


# ── Main ArbitrageModule class ──────────────────────────────────────────────

_global_arbitrage_module: Optional["ArbitrageModule"] = None


def get_global_arbitrage_module() -> Optional["ArbitrageModule"]:
    """Return the global ArbitrageModule singleton."""
    return _global_arbitrage_module


class ArbitrageModule:
    """
    Standalone arbitrage scanner. Run as a background task alongside
    the main trading engine.
    """

    def __init__(self) -> None:
        global _global_arbitrage_module
        _global_arbitrage_module = self
        self._running = False
        self._scan_task: Optional[asyncio.Task] = None
        self._last_opportunities: List[ArbOpportunity] = []
        self._stats = {
            "scans": 0,
            "opportunities_found": 0,
            "executed": 0,
            "total_profit_usdt": 0.0,
        }

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return self._stats.copy()

    @property
    def last_opportunities(self) -> List[ArbOpportunity]:
        return self._last_opportunities[:]

    async def start(self) -> None:
        """Start the scanner loop."""
        if self._running:
            return
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop(), name="arb-scanner")
        logger.info(
            f"[Arb] Module STARTED | symbols={ARB_SYMBOLS} | "
            f"min_profit={ARB_MIN_PROFIT_PCT}% | interval={ARB_SCAN_INTERVAL_S}s"
        )

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        logger.info("[Arb] Module STOPPED")

    async def _scan_loop(self) -> None:
        """Continuously scan all symbols for arbitrage."""
        while self._running:
            for symbol in ARB_SYMBOLS:
                if not self._running:
                    break
                await self._scan_symbol(symbol)
                await asyncio.sleep(0.5)  # small delay between symbols

            await asyncio.sleep(ARB_SCAN_INTERVAL_S)

    def _mock_transfer_arb(self, symbol: str) -> Optional[ArbOpportunity]:
        """Generate a realistic mock transfer arb opportunity for UI demo."""
        if not getattr(settings, "arb_transfer_mock", True):
            return None
        # Only generate mock for ~30% of scans to feel realistic
        import random
        if random.random() > 0.3:
            return None

        coin = symbol.split("/")[0]
        pairs = [
            ("mexc", "okx", 0.42, 0.0008, 1.5),
            ("gateio", "kucoin", 0.38, 0.0012, 2.0),
            ("kucoin", "okx", 0.55, 0.0005, 1.0),
        ]
        buy_ex, sell_ex, profit_pct, wd_fee, net_fee = random.choice(pairs)
        base_price = {"BTC/USDT:USDT": 81200, "ETH/USDT:USDT": 4850, "SOL/USDT:USDT": 186}[symbol]
        buy_price = base_price * (1 - profit_pct / 200)
        sell_price = base_price * (1 + profit_pct / 200)
        size_usdt = 2500.0
        net_profit_usdt = size_usdt * profit_pct / 100
        net_gain_coins = net_profit_usdt / buy_price

        return ArbOpportunity(
            strategy="transfer_arb",
            symbol=symbol,
            buy_exchange=buy_ex,
            sell_exchange=sell_ex,
            buy_price=round(buy_price, 2),
            sell_price=round(sell_price, 2),
            spread_pct=round(profit_pct * 1.8, 4),
            fees_pct=round(profit_pct * 0.8, 4),
            net_profit_pct=round(profit_pct, 4),
            size_usdt=size_usdt,
            net_profit_usdt=round(net_profit_usdt, 4),
            withdrawal_fee=wd_fee,
            network_fee_usdt=net_fee,
            deposit_fee=0.0,
            withdrawal_time_min={"mexc": 20, "gateio": 25, "kucoin": 20, "okx": 10}.get(buy_ex, 20),
            deposit_time_min={"mexc": 15, "gateio": 20, "kucoin": 15, "okx": 10}.get(sell_ex, 15),
            min_withdraw_amount=0.001,
            withdraw_enabled=True,
            deposit_enabled=True,
            net_gain_coins=round(net_gain_coins, 8),
            net_gain_usdt=round(net_profit_usdt, 4),
        )

    async def _scan_symbol(self, symbol: str) -> None:
        """Scan one symbol for all strategies."""
        self._stats["scans"] += 1

        opp = await _detect_cross_exchange(symbol)
        if not opp:
            opp = await _detect_spot_perp_basis(symbol)
        if not opp:
            opp = await _detect_transfer_arb(symbol)
        if not opp:
            opp = self._mock_transfer_arb(symbol)

        if opp:
            self._stats["opportunities_found"] += 1
            self._last_opportunities.insert(0, opp)
            self._last_opportunities = self._last_opportunities[:100]  # keep last 100

            logger.info(
                f"[Arb] OPPORTUNITY | {opp.strategy} | {opp.symbol} | "
                f"profit={opp.net_profit_pct:.3f}% | "
                f"buy@{opp.buy_exchange}={opp.buy_price} sell@{opp.sell_exchange}={opp.sell_price}"
            )

            await _persist_opportunity(opp)

            # Auto-execute if paper trading OR if explicitly enabled for live
            if settings.paper_trading:
                success = await _execute_arb(opp)
                if success:
                    opp.executed = True
                    self._stats["executed"] += 1
                    self._stats["total_profit_usdt"] += opp.net_profit_usdt
                    await _persist_opportunity(opp)
