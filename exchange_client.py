"""
exchange_client.py
─────────────────────────────────────────────────────────────────────────────
Async CCXT wrapper that supports:
  • Opening long on exchange A + short on exchange B simultaneously
  • Hedge-mode on a single exchange
  • Paper-trading simulation (no real orders placed)
  • Graceful reconnect / error handling

BUG FIXES (v2):
  • BUG 1 FIXED: open_long_leg() contained the line
        leg.status = LegState.__fields__
    which assigned the Pydantic model's internal __fields__ dict to the
    status field instead of a LegStatus enum value.  Any concurrent reader
    between that line and the correct assignment six lines later would see
    a dict instead of a LegStatus, causing AttributeError / comparison
    failures.  The corrupt intermediate assignment has been removed
    entirely — leg.status = LegStatus.OPEN at the bottom of the function
    is now the ONLY status assignment in open_long_leg().

  • BUG 6 FIXED: place_market_order() accepted a `reduce_only` parameter
    but NEVER forwarded it to the exchange params dict.  In live trading
    this would open a NEW position in the opposite direction instead of
    closing the existing one (a critical financial bug).  The fix adds:
        if reduce_only:
            params["reduceOnly"] = True
    before the exchange call, ensuring the exchange receives the flag.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import ccxt.async_support as ccxt
from loguru import logger

from config import settings
from models import FundingRate, LegState, LegStatus, MarketSnapshot, Side


# ─────────────────────────────────────────────────────────────────────────────
# Exchange factory
# ─────────────────────────────────────────────────────────────────────────────

_exchange_cache: Dict[str, ccxt.Exchange] = {}


async def get_exchange(exchange_id: str) -> ccxt.Exchange:
    """
    Return (or create) a cached async CCXT exchange instance.
    Uses credentials from config.settings.
    """
    if exchange_id in _exchange_cache:
        return _exchange_cache[exchange_id]

    kwargs = settings.get_exchange_kwargs(exchange_id)
    exchange_class = getattr(ccxt, exchange_id)
    exchange: ccxt.Exchange = exchange_class(kwargs)

    # Load markets once at startup
    await exchange.load_markets()

    _exchange_cache[exchange_id] = exchange
    logger.info(f"[Exchange] Initialized {exchange_id} (sandbox={kwargs.get('sandbox', False)})")
    return exchange


async def close_all_exchanges() -> None:
    """Gracefully close all cached exchange connections."""
    for eid, ex in _exchange_cache.items():
        try:
            await ex.close()
            logger.info(f"[Exchange] Closed {eid}")
        except Exception as e:
            logger.warning(f"[Exchange] Error closing {eid}: {e}")
    _exchange_cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Market data helpers
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_EXCHANGES = ["okx", "kucoin", "gateio", "kraken", "mexc"]


async def _get_public_exchange(exchange_id: str) -> ccxt.Exchange:
    """Create a CCXT exchange instance for public data (no API keys, no sandbox)."""
    cache_key = f"_public_{exchange_id}"
    if cache_key in _exchange_cache:
        return _exchange_cache[cache_key]
    exchange_class = getattr(ccxt, exchange_id)
    ex: ccxt.Exchange = exchange_class({"enableRateLimit": True})
    await ex.load_markets()
    _exchange_cache[cache_key] = ex
    logger.info(f"[Exchange] Initialized public {exchange_id}")
    return ex


async def fetch_market_snapshot(exchange_id: str, symbol: str) -> MarketSnapshot:
    """
    Fetch best bid/ask, mark price, OI, funding rate in one call.
    Falls back to public exchanges if the configured exchange fails.
    """
    errors: List[str] = []
    # Try configured exchange first, then fallbacks
    for ex_id in [exchange_id] + [e for e in _FALLBACK_EXCHANGES if e != exchange_id]:
        try:
            if ex_id == exchange_id:
                ex = await get_exchange(ex_id)
            else:
                ex = await _get_public_exchange(ex_id)
            ticker = await ex.fetch_ticker(symbol)
            funding_info: Dict = {}
            try:
                funding_info = await ex.fetch_funding_rate(symbol)
            except Exception:
                pass

            return MarketSnapshot(
                symbol=symbol,
                bid=ticker.get("bid") or ticker.get("last", 0),
                ask=ticker.get("ask") or ticker.get("last", 0),
                last=ticker.get("last", 0),
                mark_price=ticker.get("markPrice") or ticker.get("last", 0),
                index_price=ticker.get("indexPrice") or ticker.get("last", 0),
                open_interest=ticker.get("openInterest") or 0,
                funding_rate=funding_info.get("fundingRate") or 0,
                volume_24h=ticker.get("quoteVolume") or ticker.get("baseVolume") or 0,
                change_24h_pct=ticker.get("percentage") or 0,
            )
        except Exception as e:
            err_msg = f"{ex_id}: {e}"
            errors.append(err_msg)
            logger.debug(f"[Exchange] Snapshot fallback failed: {err_msg}")
            continue

    logger.error(f"[Exchange] fetch_market_snapshot failed for {symbol}: {' | '.join(errors)}")
    raise Exception(f"All exchanges failed for {symbol}: {' | '.join(errors)}")


async def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1h",
    limit: int = 200,
) -> List[List]:
    """Return raw OHLCV list [[ts, o, h, l, c, v], ...]."""
    ex = await get_exchange(exchange_id)
    bars = await ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    return bars


async def fetch_funding_rate(exchange_id: str, symbol: str) -> FundingRate:
    ex = await get_exchange(exchange_id)
    raw = await ex.fetch_funding_rate(symbol)
    return FundingRate(
        symbol=symbol,
        exchange_id=exchange_id,
        rate=raw.get("fundingRate", 0),
        next_funding_time=raw.get("fundingDatetime"),
    )


async def fetch_order_book(
    exchange_id: str, symbol: str, depth: int = 20
) -> Dict:
    ex = await get_exchange(exchange_id)
    return await ex.fetch_order_book(symbol, limit=depth)


async def fetch_currency_info(exchange_id: str, coin: str, public: bool = False) -> Optional[Dict]:
    """
    Fetch withdrawal/deposit info for a coin on an exchange.
    Returns dict with: withdrawal_fee, deposit_fee, min_withdraw,
    withdraw_enabled, deposit_enabled, networks.
    Falls back to None if exchange doesn't support fetch_currencies.
    Set public=True to use a public exchange instance (no API keys).
    """
    try:
        if public:
            ex = await _get_public_exchange(exchange_id)
        else:
            ex = await get_exchange(exchange_id)
        if not hasattr(ex, "fetch_currencies"):
            return None
        currencies = await ex.fetch_currencies()
        info = currencies.get(coin.upper()) or currencies.get(coin.lower())
        if not info:
            return None
        network_info = info.get("networks", {})
        # Pick the first network with fee info, or default
        first_net = next(iter(network_info.values()), {}) if network_info else {}
        return {
            "withdrawal_fee": first_net.get("fee", info.get("fee")),
            "deposit_fee": first_net.get("deposit_fee", 0),
            "min_withdraw": first_net.get("withdraw_minimum", info.get("limits", {}).get("withdraw", {}).get("min")),
            "withdraw_enabled": first_net.get("withdraw", info.get("withdraw", True)),
            "deposit_enabled": first_net.get("deposit", info.get("deposit", True)),
            "networks": list(network_info.keys()) if network_info else [],
        }
    except Exception as e:
        logger.debug(f"[Exchange] fetch_currency_info failed {exchange_id}/{coin}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Order helpers
# ─────────────────────────────────────────────────────────────────────────────

async def set_leverage(exchange_id: str, symbol: str, leverage: int) -> None:
    """Set leverage; silently skip if exchange doesn't support it."""
    if settings.paper_trading:
        logger.debug(f"[PaperTrade] set_leverage({exchange_id}, {symbol}, {leverage})")
        return
    ex = await get_exchange(exchange_id)
    try:
        await ex.set_leverage(leverage, symbol)
        logger.info(f"[Exchange] Leverage set to {leverage}x on {exchange_id}/{symbol}")
    except Exception as e:
        logger.warning(f"[Exchange] set_leverage skipped: {e}")


async def set_position_mode_hedge(exchange_id: str) -> None:
    """
    Enable hedge mode (dual-position) on exchanges that support it (Bybit, Binance).
    Safe to call multiple times.
    """
    if settings.paper_trading:
        return
    ex = await get_exchange(exchange_id)
    try:
        if hasattr(ex, "set_position_mode"):
            await ex.set_position_mode(True)   # True = hedge mode
            logger.info(f"[Exchange] Hedge mode enabled on {exchange_id}")
    except Exception as e:
        logger.warning(f"[Exchange] set_position_mode_hedge skipped: {e}")


async def place_market_order(
    exchange_id: str,
    symbol: str,
    side: Side,
    quantity: float,
    reduce_only: bool = False,
    params: Optional[Dict] = None,
) -> Dict:
    """
    Place a market order.  In paper-trading mode returns a synthetic fill.

    BUG 6 FIX: `reduce_only` is now correctly forwarded into the `params`
    dict as "reduceOnly": True before the exchange call.  Previously this
    parameter was accepted but NEVER passed to the exchange, which caused
    closing orders to open NEW opposite-direction positions instead of
    reducing existing ones — a critical financial bug in live trading.
    """
    params = params or {}

    # BUG 6 FIX: forward reduce_only to exchange params BEFORE any call
    if reduce_only:
        params["reduceOnly"] = True

    # Hedge-mode position side params
    if settings.same_exchange_hedge_mode:
        params["positionSide"] = "LONG" if side == Side.LONG else "SHORT"

    if settings.paper_trading:
        synthetic_id = f"PAPER-{exchange_id[:3].upper()}-{symbol[:3]}-{side.value[:1].upper()}"
        logger.info(
            f"[PaperTrade] MARKET {side.value.upper()} {quantity} {symbol} on {exchange_id}"
            + (" [reduceOnly]" if reduce_only else "")
        )
        return {
            "id": synthetic_id,
            "status": "closed",
            "average": 0,    # caller must patch with mark price
            "filled": quantity,
            "symbol": symbol,
        }

    ex = await get_exchange(exchange_id)
    ccxt_side = "buy" if side == Side.LONG else "sell"
    try:
        order = await ex.create_market_order(
            symbol=symbol,
            side=ccxt_side,
            amount=quantity,
            params=params,   # params now contains reduceOnly when applicable
        )
        logger.info(
            f"[Exchange] MARKET {ccxt_side.upper()} {quantity} {symbol} "
            f"on {exchange_id} → order_id={order['id']}"
            + (" [reduceOnly]" if reduce_only else "")
        )
        return order
    except Exception as e:
        logger.error(f"[Exchange] place_market_order failed: {e}")
        raise


async def place_stop_order(
    exchange_id: str,
    symbol: str,
    side: Side,           # side of the CLOSING order
    quantity: float,
    stop_price: float,
    order_type: str = "stop_market",
    params: Optional[Dict] = None,
) -> Optional[Dict]:
    """Place a stop-loss or take-profit order."""
    params = params or {}
    if settings.same_exchange_hedge_mode:
        params["positionSide"] = "LONG" if side == Side.SHORT else "SHORT"
        # closing long → SHORT position side, and vice versa
        params["reduceOnly"] = True

    if settings.paper_trading:
        logger.debug(
            f"[PaperTrade] STOP {side.value} {quantity} {symbol} "
            f"@ trigger={stop_price} on {exchange_id}"
        )
        return {"id": f"PAPER-STOP-{exchange_id[:3].upper()}", "status": "open"}

    ex = await get_exchange(exchange_id)
    ccxt_side = "sell" if side == Side.SHORT else "buy"
    try:
        order = await ex.create_order(
            symbol=symbol,
            type=order_type,
            side=ccxt_side,
            amount=quantity,
            price=None,
            params={"stopPrice": stop_price, **params},
        )
        logger.info(
            f"[Exchange] STOP order placed: {symbol} @ {stop_price} on {exchange_id}"
        )
        return order
    except Exception as e:
        logger.error(f"[Exchange] place_stop_order failed: {e}")
        return None


async def cancel_order(
    exchange_id: str, order_id: str, symbol: str
) -> bool:
    if settings.paper_trading:
        logger.debug(f"[PaperTrade] cancel_order {order_id}")
        return True
    ex = await get_exchange(exchange_id)
    try:
        await ex.cancel_order(order_id, symbol)
        return True
    except Exception as e:
        logger.warning(f"[Exchange] cancel_order {order_id} failed: {e}")
        return False


async def fetch_position(
    exchange_id: str, symbol: str
) -> Optional[Dict]:
    """Fetch current position for one symbol."""
    if settings.paper_trading:
        return None
    ex = await get_exchange(exchange_id)
    try:
        positions = await ex.fetch_positions([symbol])
        for pos in positions:
            if pos["symbol"] == symbol and float(pos.get("contracts", 0)) != 0:
                return pos
    except Exception as e:
        logger.warning(f"[Exchange] fetch_position failed ({exchange_id}/{symbol}): {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Composite open/close helpers used by Up-Agent & Down-Agent
# ─────────────────────────────────────────────────────────────────────────────

async def open_long_leg(leg: LegState, mark_price: float) -> LegState:
    """
    Open the long (bullish) leg on the configured long exchange.
    Applies leverage, places market order, attaches stop orders.
    Returns updated LegState.

    BUG 1 FIX: Removed the corrupt intermediate assignment:
        leg.status = LegState.__fields__
    which wrote the Pydantic model's internal __fields__ dict (a plain
    Python dict) to the status field instead of a LegStatus enum.  Any
    code reading leg.status between that line and the correct assignment
    six lines later would receive a dict and crash on comparison.  The
    correct `leg.status = LegStatus.OPEN` at the bottom of this function
    is now the ONLY status assignment.
    """
    await set_leverage(leg.exchange_id, leg.symbol, leg.leverage)

    order = await place_market_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=Side.LONG,
        quantity=leg.quantity,
    )

    entry_price = order.get("average") or mark_price
    leg.entry_price = entry_price
    leg.current_price = entry_price
    leg.order_id = order.get("id")
    leg.opened_at = datetime.utcnow()
    # NOTE: leg.status is NOT set here — it is set to LegStatus.OPEN
    # at the bottom of this function ONLY.  No intermediate assignment.

    # Attach stop-loss (close long = sell side)
    sl_price = entry_price * (1 - settings.stop_loss_pct / 100)
    await place_stop_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=Side.SHORT,   # close long = sell
        quantity=leg.quantity,
        stop_price=round(sl_price, 2),
    )

    # Attach take-profit
    tp_price = entry_price * (1 + settings.take_profit_pct / 100)
    await place_stop_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=Side.SHORT,
        quantity=leg.quantity,
        stop_price=round(tp_price, 2),
        order_type="take_profit_market",
    )

    leg.stop_loss_price = sl_price
    leg.take_profit_price = tp_price
    leg.notional_usdt = entry_price * leg.quantity
    # BUG 1 FIX: this is now the ONLY place leg.status is set in this fn
    leg.status = LegStatus.OPEN
    return leg


async def open_short_leg(leg: LegState, mark_price: float) -> LegState:
    """Open the short (bearish) leg on the configured short exchange."""
    await set_leverage(leg.exchange_id, leg.symbol, leg.leverage)

    order = await place_market_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=Side.SHORT,
        quantity=leg.quantity,
    )

    entry_price = order.get("average") or mark_price
    leg.entry_price = entry_price
    leg.current_price = entry_price
    leg.order_id = order.get("id")
    leg.opened_at = datetime.utcnow()

    sl_price = entry_price * (1 + settings.stop_loss_pct / 100)
    tp_price = entry_price * (1 - settings.take_profit_pct / 100)

    await place_stop_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=Side.LONG,    # close short = buy
        quantity=leg.quantity,
        stop_price=round(sl_price, 2),
    )
    await place_stop_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=Side.LONG,
        quantity=leg.quantity,
        stop_price=round(tp_price, 2),
        order_type="take_profit_market",
    )

    leg.stop_loss_price = sl_price
    leg.take_profit_price = tp_price
    leg.notional_usdt = entry_price * leg.quantity
    leg.status = LegStatus.OPEN
    return leg


async def close_leg_market(leg: LegState) -> LegState:
    """
    Close a leg at market price.
    Uses reduce_only=True to ensure the order closes the existing position
    rather than opening a new one in the opposite direction.
    """
    close_side = Side.SHORT if leg.side == Side.LONG else Side.LONG
    await place_market_order(
        exchange_id=leg.exchange_id,
        symbol=leg.symbol,
        side=close_side,
        quantity=leg.quantity,
        reduce_only=True,   # BUG 6 FIX: explicitly pass reduce_only=True here
    )
    leg.realized_pnl = leg.unrealized_pnl
    leg.unrealized_pnl = 0.0
    leg.status = LegStatus.CLOSED
    leg.closed_at = datetime.utcnow()
    logger.info(f"[Exchange] Leg {leg.leg_id} ({leg.side}) closed. PnL={leg.realized_pnl:.2f}")
    return leg


async def open_both_legs_concurrently(
    long_leg: LegState,
    short_leg: LegState,
    mark_price: float,
) -> Tuple[LegState, LegState]:
    """
    Fire both legs at the same time using asyncio.gather().
    This minimises slippage asymmetry between the two legs.

    IMPORTANT: This function takes pre-constructed LegState objects and
    opens them directly.  It does NOT call UpAgent.open_leg() or
    DownAgent.open_leg() — those methods also attach the leg to the
    package, so calling them AND this function would double-execute.
    The orchestrator's node_execute() uses this function exclusively
    with fresh LegState objects (see orchestrator.py BUG 3 fix).
    """
    logger.info(
        f"[Execution] Opening composite package: LONG {long_leg.symbol} on "
        f"{long_leg.exchange_id} + SHORT {short_leg.symbol} on {short_leg.exchange_id}"
    )
    long_result, short_result = await asyncio.gather(
        open_long_leg(long_leg, mark_price),
        open_short_leg(short_leg, mark_price),
        return_exceptions=False,
    )
    return long_result, short_result
