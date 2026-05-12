"""
supabase_client.py
─────────────────────────────────────────────────────────────────────────────
Supabase PostgreSQL client for the DualAgentHedgeSystem.
Replaces SQLite/SQLAlchemy with Supabase for true SaaS multi-tenancy.
Uses PostgREST for CRUD and enforces RLS via auth.uid() in service role.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from loguru import logger
from supabase import create_client, Client

from config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Singleton Supabase client
# ─────────────────────────────────────────────────────────────────────────────

_supabase: Optional[Client] = None


def get_supabase() -> Client:
    """Return the singleton Supabase client (service role for backend ops)."""
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL", "")
        service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not service_key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
            )
        _supabase = create_client(url, service_key)
        logger.info("[Supabase] Client initialized")
    return _supabase


# ─────────────────────────────────────────────────────────────────────────────
# Trade operations (RLS enforced by PostgreSQL policies)
# ─────────────────────────────────────────────────────────────────────────────

async def save_trade(
    package_id: str,
    user_id: str,
    symbol: str,
    status: str,
    combined_pnl: float = 0.0,
    risk_budget: float = 0.0,
    close_reason: str = "",
    consensus_json: str = "{}",
    created_at: Optional[datetime] = None,
    closed_at: Optional[datetime] = None,
    notes: str = "[]",
    long_exchange: Optional[str] = None,
    short_exchange: Optional[str] = None,
    long_pnl: float = 0.0,
    short_pnl: float = 0.0,
    long_qty: Optional[float] = None,
    short_qty: Optional[float] = None,
    long_notional: Optional[float] = None,
    short_notional: Optional[float] = None,
    long_entry: Optional[float] = None,
    short_entry: Optional[float] = None,
    long_leverage: Optional[int] = None,
    short_leverage: Optional[int] = None,
    funding_paid: float = 0.0,
) -> bool:
    """Upsert a trade record. RLS ensures user isolation at the DB level."""
    try:
        sb = get_supabase()
        data = {
            "package_id": package_id,
            "user_id": user_id,
            "symbol": symbol,
            "status": status,
            "combined_pnl": combined_pnl,
            "risk_budget": risk_budget,
            "close_reason": close_reason,
            "consensus_json": consensus_json,
            "created_at": (created_at or datetime.utcnow()).isoformat(),
            "closed_at": closed_at.isoformat() if closed_at else None,
            "notes": notes,
            "long_exchange": long_exchange,
            "short_exchange": short_exchange,
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "long_qty": long_qty,
            "short_qty": short_qty,
            "long_notional": long_notional,
            "short_notional": short_notional,
            "long_entry": long_entry,
            "short_entry": short_entry,
            "long_leverage": long_leverage,
            "short_leverage": short_leverage,
            "funding_paid": funding_paid,
        }
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        sb.table("trades").upsert(data).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] save_trade error: {e}")
        return False


async def get_recent_trades(user_id: str, limit: int = 50) -> List[Dict]:
    """Fetch recent trades for a user. RLS policy enforces user_id = auth.uid()."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("trades")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error(f"[Supabase] get_recent_trades error: {e}")
        return []


async def get_trade(user_id: str, package_id: str) -> Optional[Dict]:
    """Fetch a single trade by package_id."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("trades")
            .select("*")
            .eq("user_id", user_id)
            .eq("package_id", package_id)
            .single()
            .execute()
        )
        return resp.data
    except Exception as e:
        logger.error(f"[Supabase] get_trade error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Equity operations
# ─────────────────────────────────────────────────────────────────────────────

async def save_equity_snapshot(
    user_id: str,
    equity: float,
    pnl_today: float = 0.0,
    drawdown_pct: float = 0.0,
) -> bool:
    """Store an equity snapshot for a user."""
    try:
        sb = get_supabase()
        sb.table("equity_history").insert({
            "user_id": user_id,
            "equity": equity,
            "pnl_today": pnl_today,
            "drawdown_pct": drawdown_pct,
        }).execute()
        # Prune old records
        sb.rpc("prune_old_equity").execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] save_equity_snapshot error: {e}")
        return False


async def get_equity_history(user_id: str, days: int = 30) -> List[Dict]:
    """Return equity snapshots for the last N days."""
    try:
        sb = get_supabase()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        resp = (
            sb.table("equity_history")
            .select("*")
            .eq("user_id", user_id)
            .gte("timestamp", since)
            .order("timestamp", asc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error(f"[Supabase] get_equity_history error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Settings operations
# ─────────────────────────────────────────────────────────────────────────────

async def set_user_setting(user_id: str, key: str, value: str) -> bool:
    """Upsert a user setting."""
    try:
        sb = get_supabase()
        sb.table("user_settings").upsert({
            "user_id": user_id,
            "key": key,
            "value": value,
            "updated_at": datetime.utcnow().isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] set_user_setting error: {e}")
        return False


async def get_user_setting(user_id: str, key: str) -> Optional[str]:
    """Fetch a single user setting."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("user_settings")
            .select("value")
            .eq("user_id", user_id)
            .eq("key", key)
            .single()
            .execute()
        )
        return resp.data["value"] if resp.data else None
    except Exception:
        return None


async def get_all_user_settings(user_id: str) -> Dict[str, str]:
    """Fetch all settings for a user."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("user_settings")
            .select("key, value")
            .eq("user_id", user_id)
            .execute()
        )
        return {r["key"]: r["value"] for r in (resp.data or [])}
    except Exception as e:
        logger.error(f"[Supabase] get_all_user_settings error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Custom exchanges
# ─────────────────────────────────────────────────────────────────────────────

async def add_custom_exchange(
    user_id: str,
    exchange_id: str,
    api_key: str = "",
    api_secret: str = "",
    api_passphrase: str = "",
    testnet: bool = True,
) -> bool:
    """Add a custom exchange for a user."""
    try:
        sb = get_supabase()
        sb.table("custom_exchanges").upsert({
            "user_id": user_id,
            "exchange_id": exchange_id,
            "api_key": api_key,
            "api_secret": api_secret,
            "api_passphrase": api_passphrase,
            "testnet": testnet,
        }).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] add_custom_exchange error: {e}")
        return False


async def get_custom_exchanges(user_id: str) -> List[Dict]:
    """Fetch all custom exchanges for a user."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("custom_exchanges")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error(f"[Supabase] get_custom_exchanges error: {e}")
        return []


async def delete_custom_exchange(user_id: str, exchange_id: str) -> bool:
    """Delete a custom exchange for a user."""
    try:
        sb = get_supabase()
        sb.table("custom_exchanges").delete().eq("user_id", user_id).eq(
            "exchange_id", exchange_id
        ).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] delete_custom_exchange error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Agent votes
# ─────────────────────────────────────────────────────────────────────────────

async def save_agent_vote(
    user_id: str,
    agent_id: str,
    role: str,
    symbol: str,
    direction: str,
    confidence: float,
) -> bool:
    """Store an agent vote for a user."""
    try:
        sb = get_supabase()
        sb.table("agent_votes").insert({
            "user_id": user_id,
            "agent_id": agent_id,
            "role": role,
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence,
        }).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] save_agent_vote error: {e}")
        return False


async def get_agent_accuracy(user_id: str, days: int = 30) -> List[Dict]:
    """Return accuracy stats per agent role for a user."""
    try:
        sb = get_supabase()
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        # Use raw SQL via RPC for complex aggregation
        resp = sb.rpc(
            "get_agent_accuracy",
            {"p_user_id": user_id, "p_days": days},
        ).execute()
        return resp.data or []
    except Exception as e:
        logger.error(f"[Supabase] get_agent_accuracy error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Arbitrage
# ─────────────────────────────────────────────────────────────────────────────

async def save_arb_opportunity(user_id: str, opp: dict) -> bool:
    """Persist an arbitrage opportunity."""
    try:
        sb = get_supabase()
        data = {
            "id": opp.get("id", f"{opp['symbol']}-{opp['strategy']}-{datetime.utcnow().timestamp()}"),
            "user_id": user_id,
            "strategy": opp["strategy"],
            "symbol": opp["symbol"],
            "buy_exchange": opp["buy_exchange"],
            "sell_exchange": opp["sell_exchange"],
            "buy_price": opp.get("buy_price", 0.0),
            "sell_price": opp.get("sell_price", 0.0),
            "spread_pct": opp.get("spread_pct", 0.0),
            "fees_pct": opp.get("fees_pct", 0.0),
            "net_profit_pct": opp.get("net_profit_pct", 0.0),
            "size_usdt": opp.get("size_usdt", 0.0),
            "net_profit_usdt": opp.get("net_profit_usdt", 0.0),
            "executed": opp.get("executed", False),
            "timestamp": opp.get("timestamp", datetime.utcnow().isoformat()),
        }
        # Add optional transfer arb fields
        for key in ["funding_rate", "withdrawal_fee", "network_fee_usdt", "deposit_fee",
                    "withdrawal_time_min", "deposit_time_min", "min_withdraw_amount",
                    "withdraw_enabled", "deposit_enabled", "net_gain_coins", "net_gain_usdt"]:
            if key in opp:
                data[key] = opp[key]
        sb.table("arb_opportunities").upsert(data).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] save_arb_opportunity error: {e}")
        return False


async def get_recent_arb_opportunities(
    user_id: str, limit: int = 100, since: Optional[datetime] = None
) -> List[Dict]:
    """Return recent arbitrage opportunities for a user."""
    try:
        sb = get_supabase()
        query = (
            sb.table("arb_opportunities")
            .select("*")
            .eq("user_id", user_id)
            .order("timestamp", desc=True)
            .limit(limit)
        )
        if since:
            query = query.gte("timestamp", since.isoformat())
        resp = query.execute()
        return resp.data or []
    except Exception as e:
        logger.error(f"[Supabase] get_recent_arb_opportunities error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Profile / User management
# ─────────────────────────────────────────────────────────────────────────────

async def get_profile(user_id: str) -> Optional[Dict]:
    """Fetch a user's profile."""
    try:
        sb = get_supabase()
        resp = (
            sb.table("profiles")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return resp.data
    except Exception as e:
        logger.error(f"[Supabase] get_profile error: {e}")
        return None


async def update_profile(user_id: str, updates: Dict) -> bool:
    """Update a user's profile."""
    try:
        sb = get_supabase()
        sb.table("profiles").update(updates).eq("id", user_id).execute()
        return True
    except Exception as e:
        logger.error(f"[Supabase] update_profile error: {e}")
        return False
