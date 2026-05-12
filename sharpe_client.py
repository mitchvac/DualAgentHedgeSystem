"""
sharpe_client.py
─────────────────────────────────────────────────────────────────────────────
Thin HTTP client for Sharpe.ai arbitrage data.
Fetches cross-exchange price gaps, funding rates, and spot-perp spreads.
No API key required for basic endpoints; free tier with optional Bearer token.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from loguru import logger

from config import settings

SHARPE_BASE_URL = "https://api.sharpe.ai/v1"
SHARPE_API_KEY: Optional[str] = getattr(settings, "sharpe_api_key", None)

_sharpe_client: Optional[httpx.AsyncClient] = None


async def _get_client() -> httpx.AsyncClient:
    global _sharpe_client
    if _sharpe_client is None:
        headers = {}
        if SHARPE_API_KEY:
            headers["Authorization"] = f"Bearer {SHARPE_API_KEY}"
        _sharpe_client = httpx.AsyncClient(
            base_url=SHARPE_BASE_URL,
            headers=headers,
            timeout=15.0,
        )
    return _sharpe_client


async def close_sharpe_client() -> None:
    global _sharpe_client
    if _sharpe_client:
        await _sharpe_client.aclose()
        _sharpe_client = None


async def fetch_cross_exchange_gaps(symbol: Optional[str] = None, min_spread_pct: float = 0.1) -> List[Dict]:
    """
    Fetch cross-exchange price gaps from Sharpe.ai.
    Returns list of dicts with: symbol, buy_exchange, sell_exchange,
    buy_price, sell_price, spread_pct.
    """
    try:
        client = await _get_client()
        params = {"minSpreadPct": min_spread_pct}
        if symbol:
            params["symbol"] = symbol
        resp = await client.get("/arbitrage/cross-exchange", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("opportunities", [])
    except Exception as e:
        logger.debug(f"[Sharpe] cross-exchange fetch failed: {e}")
        return []


async def fetch_funding_arbitrage(symbol: Optional[str] = None) -> List[Dict]:
    """Fetch funding rate arbitrage opportunities."""
    try:
        client = await _get_client()
        params = {}
        if symbol:
            params["symbol"] = symbol
        resp = await client.get("/arbitrage/funding", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("opportunities", [])
    except Exception as e:
        logger.debug(f"[Sharpe] funding arb fetch failed: {e}")
        return []


async def fetch_spot_perp_spreads(symbol: Optional[str] = None) -> List[Dict]:
    """Fetch spot-perp basis spreads."""
    try:
        client = await _get_client()
        params = {}
        if symbol:
            params["symbol"] = symbol
        resp = await client.get("/arbitrage/spot-perp", params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("opportunities", [])
    except Exception as e:
        logger.debug(f"[Sharpe] spot-perp fetch failed: {e}")
        return []
