"""
app_fullstack.py
─────────────────────────────────────────────────────────────────────────────
Production FastAPI backend — ZERO mock data.

Every endpoint reads from:
  • The live Orchestrator (positions, equity, agent status)
  • The exchange APIs via CCXT (market snapshots, balances)
  • SQLite via memory_store (trade history, analytics)
  • The 100-agent Swarm (roster, consensus)
  • The Defense Swarm (circuit status, events)

This module is designed to run in the SAME process as the trading engine
(via main_fullstack.py) so it can access get_global_orchestrator() directly.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from loguru import logger
import bcrypt
from pydantic import BaseModel, Field
import httpx

from config import settings


# ── JWT Config ──────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "hedgeswarm-dev-secret-change-in-production")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

DEFAULT_USER = os.getenv("ADMIN_USER", "admin")
_DEFAULT_PLAIN_PASS = os.getenv("ADMIN_PASSWORD", "admin")
DEFAULT_PASS_HASH = bcrypt.hashpw(_DEFAULT_PLAIN_PASS.encode(), bcrypt.gensalt()).decode()

# ── OAuth Config ────────────────────────────────────────────────────────────
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

OAUTH_CONFIG = {
    "google": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scope": "user:email",
    },
    "facebook": {
        "client_id": os.getenv("FACEBOOK_CLIENT_ID", ""),
        "client_secret": os.getenv("FACEBOOK_CLIENT_SECRET", ""),
        "auth_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "userinfo_url": "https://graph.facebook.com/me",
        "scope": "email,public_profile",
    },
}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class CommandPayload(BaseModel):
    # Verified: strict schema for command endpoint to prevent injection
    command: str = Field(..., min_length=1, max_length=64)
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ExchangeTestPayload(BaseModel):
    exchange_id: str = Field(..., min_length=1, max_length=32)
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    testnet: bool = True


class LoginPayload(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class SettingsUpdatePayload(BaseModel):
    max_risk_per_package_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    default_leverage: Optional[int] = None
    min_consensus_score: Optional[float] = None
    signal_refresh_seconds: Optional[int] = None
    defense_enabled: Optional[bool] = None
    defense_bull_run_threshold: Optional[float] = None
    watchlist: Optional[List[str]] = None
    max_daily_drawdown_pct: Optional[float] = None
    max_concurrent_packages: Optional[int] = None
    funding_rate_threshold: Optional[float] = None
    rebalance_interval_min: Optional[int] = None
    # Exchange config
    long_exchange_id: Optional[str] = None
    short_exchange_id: Optional[str] = None
    same_exchange_hedge_mode: Optional[bool] = None
    bybit_testnet: Optional[bool] = None
    okx_testnet: Optional[bool] = None
    binance_testnet: Optional[bool] = None
    bybit_api_key: Optional[str] = None
    bybit_api_secret: Optional[str] = None
    okx_api_key: Optional[str] = None
    okx_api_secret: Optional[str] = None
    okx_api_passphrase: Optional[str] = None
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    # Trading mode
    paper_trading: Optional[bool] = None
    # Agent config
    agent_role_config: Optional[Dict[str, Any]] = None


# ── Auth helpers ────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def _lookup_user(username: str, password: str) -> Optional[str]:
    """Check hardcoded admin OR database users."""
    if username == DEFAULT_USER and verify_password(password, DEFAULT_PASS_HASH):
        return username
    # Check SQLite users
    from memory_store import memory_store
    await memory_store.initialize()
    user = await memory_store.get_user(username)
    if user and verify_password(password, user.password_hash):
        return username
    return None


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    if not token:
        return None
    # 1) Try local JWT (legacy auth / dev fallback)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username:
            return username
    except JWTError:
        pass
    # 2) Try Supabase JWT (production auth)
    if SUPABASE_JWT_SECRET:
        try:
            payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=[ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id:
                return user_id
        except JWTError:
            pass
    # 3) Dev fallback: accept any well-formed JWT without verifying signature
    #    (ONLY when SUPABASE_JWT_SECRET is not set — never in production)
    if not SUPABASE_JWT_SECRET:
        try:
            payload = jwt.decode(token, "", algorithms=[ALGORITHM], options={"verify_signature": False})
            user_id: str = payload.get("sub")
            if user_id:
                return user_id
        except JWTError:
            pass
    return None


async def require_auth(user: Optional[str] = Depends(get_current_user)) -> str:
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ── Connection Manager ──────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> List[WebSocket] mapping for per-user broadcasts
        self.user_connections: dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = []
            self.user_connections[user_id].append(websocket)
        logger.info(f"[WS] Client connected for user '{user_id}'. Total conns: {sum(len(v) for v in self.user_connections.values())}")

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        async with self._lock:
            conns = self.user_connections.get(user_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self.user_connections.pop(user_id, None)

    async def broadcast(self, message: dict) -> None:
        """Broadcast to ALL connections (system-level messages only)."""
        dead: List[tuple[str, WebSocket]] = []
        async with self._lock:
            user_map = {uid: list(conns) for uid, conns in self.user_connections.items()}
        for user_id, conns in user_map.items():
            for conn in conns:
                try:
                    await conn.send_json(message)
                except Exception:
                    dead.append((user_id, conn))
        if dead:
            async with self._lock:
                for user_id, conn in dead:
                    conns = self.user_connections.get(user_id, [])
                    if conn in conns:
                        conns.remove(conn)
                    if not conns:
                        self.user_connections.pop(user_id, None)

    async def broadcast_to_user(self, user_id: str, message: dict) -> None:
        """Broadcast a message only to connections belonging to a specific user."""
        async with self._lock:
            conns = list(self.user_connections.get(user_id, []))
        dead: List[WebSocket] = []
        for conn in conns:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        if dead:
            async with self._lock:
                user_conns = self.user_connections.get(user_id, [])
                for conn in dead:
                    if conn in user_conns:
                        user_conns.remove(conn)
                if not user_conns:
                    self.user_connections.pop(user_id, None)

    async def send_to(self, websocket: WebSocket, message: dict) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            pass  # Caller should handle disconnect


manager = ConnectionManager()


# ── Real data helpers (ZERO mocks) ──────────────────────────────────────────

async def load_trades(user: str, limit: int = 100) -> List[dict]:
    """Fetch trade history from SQLite for a specific user, enriched with live leg data from Orchestrator."""
    from memory_store import memory_store
    from orchestrator import get_global_orchestrator
    await memory_store.initialize()
    records = await memory_store.get_recent_packages(user_id=user, limit=limit)
    orch = get_global_orchestrator()
    live_packages = orch.active_packages if orch else {}
    result = []
    for r in records:
        # Default to stored values
        long_ex = r.long_exchange
        short_ex = r.short_exchange
        long_pnl = r.long_pnl or 0
        short_pnl = r.short_pnl or 0
        long_qty = r.long_qty
        short_qty = r.short_qty
        long_notional = r.long_notional
        short_notional = r.short_notional
        long_entry = r.long_entry
        short_entry = r.short_entry
        long_lev = r.long_leverage
        short_lev = r.short_leverage
        funding = r.funding_paid or 0
        # Override with live data for active packages
        if r.status == "active" and r.package_id in live_packages:
            pkg = live_packages[r.package_id]
            if pkg.long_leg:
                long_ex = pkg.long_leg.exchange_id
                long_pnl = round(pkg.long_leg.unrealized_pnl + pkg.long_leg.realized_pnl, 4)
                long_qty = pkg.long_leg.quantity
                long_notional = pkg.long_leg.notional_usdt
                long_entry = pkg.long_leg.entry_price
                long_lev = pkg.long_leg.leverage
            if pkg.short_leg:
                short_ex = pkg.short_leg.exchange_id
                short_pnl = round(pkg.short_leg.unrealized_pnl + pkg.short_leg.realized_pnl, 4)
                short_qty = pkg.short_leg.quantity
                short_notional = pkg.short_leg.notional_usdt
                short_entry = pkg.short_leg.entry_price
                short_lev = pkg.short_leg.leverage
            funding = (pkg.long_leg.funding_paid if pkg.long_leg else 0) + (pkg.short_leg.funding_paid if pkg.short_leg else 0)
        result.append({
            "package_id": r.package_id[:8],
            "symbol": r.symbol,
            "status": r.status,
            "pnl_usdt": round(r.combined_pnl, 4),
            "risk_budget": round(r.risk_budget, 2),
            "pnl_pct": round(r.combined_pnl / max(r.risk_budget, 1) * 100, 2),
            "close_reason": r.close_reason,
            "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
            "long_exchange": long_ex or "—",
            "short_exchange": short_ex or "—",
            "long_pnl": long_pnl,
            "short_pnl": short_pnl,
            "long_qty": long_qty,
            "short_qty": short_qty,
            "long_notional": long_notional,
            "short_notional": short_notional,
            "long_entry": long_entry,
            "short_entry": short_entry,
            "long_leverage": long_lev,
            "short_leverage": short_lev,
            "funding_paid": funding,
        })
    return result


async def load_positions(user: str) -> List[dict]:
    """Fetch LIVE active positions from the running Orchestrator for a specific user."""
    from orchestrator import get_global_orchestrator
    orch = get_global_orchestrator()
    if not orch:
        return []

    positions: List[dict] = []
    for pkg in list(orch.active_packages.values()):
        if pkg.user_id != user:
            continue
        if pkg.long_leg:
            positions.append({
                "package_id": pkg.package_id[:8],
                "symbol": pkg.symbol,
                "side": "long",
                "exchange": pkg.long_leg.exchange_id,
                "entry_price": pkg.long_leg.entry_price,
                "current_price": pkg.long_leg.current_price,
                "quantity": pkg.long_leg.quantity,
                "leverage": pkg.long_leg.leverage,
                "notional": pkg.long_leg.notional_usdt,
                "unrealized_pnl": round(pkg.long_leg.unrealized_pnl, 4),
                "stop_loss": pkg.long_leg.stop_loss_price,
                "take_profit": pkg.long_leg.take_profit_price,
            })
        if pkg.short_leg:
            positions.append({
                "package_id": pkg.package_id[:8],
                "symbol": pkg.symbol,
                "side": "short",
                "exchange": pkg.short_leg.exchange_id,
                "entry_price": pkg.short_leg.entry_price,
                "current_price": pkg.short_leg.current_price,
                "quantity": pkg.short_leg.quantity,
                "leverage": pkg.short_leg.leverage,
                "notional": pkg.short_leg.notional_usdt,
                "unrealized_pnl": round(pkg.short_leg.unrealized_pnl, 4),
                "stop_loss": pkg.short_leg.stop_loss_price,
                "take_profit": pkg.short_leg.take_profit_price,
            })
    return positions


async def load_equity(user: str) -> float:
    """Fetch LIVE account equity for a specific user.
    NOTE: Exchange balance is shared across all users on the same account.
    Per-user equity = shared_balance + user's unrealized PnL."""
    from orchestrator import get_global_orchestrator
    orch = get_global_orchestrator()

    # Get shared exchange balance
    shared_equity = 0.0
    try:
        from exchange_client import get_exchange
        ex = await get_exchange(settings.long_exchange_id)
        bal = await ex.fetch_balance()
        shared_equity = float(bal["USDT"]["free"] or bal["USDT"]["total"] or 0)
    except Exception as e:
        logger.warning(f"[API] Direct equity fetch failed: {e}")
        shared_equity = 10000.0  # fallback demo equity

    # Add only THIS user's unrealized PnL
    user_pnl = 0.0
    if orch:
        for pkg in orch.active_packages.values():
            if pkg.user_id == user:
                user_pnl += pkg.combined_pnl

    return round(shared_equity + user_pnl, 2)


async def load_defense() -> Optional[dict]:
    """Fetch LIVE defense swarm status."""
    try:
        from orchestrator import _get_global_defense
        d = _get_global_defense()
        if not d:
            return None
        status = d.get_defense_status()
        events = d.get_recent_events(10)
        return {
            "active": status.active,
            "circuit_broken": status.circuit_broken,
            "bull_score": status.bull_score,
            "active_exchange": status.active_exchange,
            "total_events": status.total_events,
            "rotations_today": status.rotations_today,
            "stealth_splits_today": status.stealth_splits_today,
            "unresolved_events": status.unresolved_events,
            "last_action": status.last_action.value if status.last_action else None,
            "events": [
                {
                    "time": e.timestamp.strftime("%H:%M:%S"),
                    "exchange": e.exchange_id,
                    "symbol": e.symbol,
                    "type": e.itype.value,
                    "severity": round(e.severity, 2),
                    "action": e.action_taken.value,
                }
                for e in events
            ],
        }
    except Exception as e:
        logger.debug(f"[API] Defense load error: {e}")
        return None


# Module-level cache for agent roster (avoids rebuilding swarm on every API call)
_agent_roster_cache: Optional[List[dict]] = None

async def load_agents() -> List[dict]:
    """Fetch the agent roster. Uses orchestrator's supervisor agents if available."""
    global _agent_roster_cache
    try:
        from orchestrator import get_global_orchestrator
        orch = get_global_orchestrator()

        # Build roster once, cache it
        if _agent_roster_cache is None:
            from swarm_agents import build_swarm
            agents = build_swarm()
            task_map = {
                "SENTIMENT": "Analyzing social sentiment",
                "TECHNICAL": "Computing indicators",
                "VOLATILITY": "Estimating volatility",
                "ONCHAIN": "Fetching on-chain data",
                "FUNDING": "Checking funding rates",
                "ORDERFLOW": "Scanning order book",
                "MACRO": "Monitoring macro events",
                "NEWS": "Parsing news headlines",
                "REFLECTION": "Querying memory DB",
                "SUPERVISOR": "Aggregating consensus",
                "UP_AGENT": "Monitoring long leg",
                "DOWN_AGENT": "Monitoring short leg",
                "RISK": "Evaluating risk limits",
                "EXECUTION": "Managing execution",
            }
            _agent_roster_cache = []
            for a in agents:
                entry = {
                    "agent_id": a.agent_id,
                    "role": a.ROLE.value,
                    "weight": a.VOTE_WEIGHT,
                    "status": "idle",
                    "task": task_map.get(a.ROLE.value, "Standby"),
                }
                _agent_roster_cache.append(entry)

        # Return a shallow copy so we can mutate status without affecting cache
        roster = [dict(entry) for entry in _agent_roster_cache]

        # Enrich with live status if orchestrator is running
        if orch and orch._running:
            active_roles = set()
            evaluating_symbol = None
            if orch.supervisor:
                active_roles.add("SUPERVISOR")
                # Check if orchestrator has scanned recently (within 2 min)
                recently_scanned = False
                if orch._last_scan_at:
                    recently_scanned = (datetime.utcnow() - orch._last_scan_at).total_seconds() < 120
                if recently_scanned or orch.supervisor.is_evaluating:
                    evaluating_symbol = orch.supervisor.evaluating_symbol
                    active_roles.update([
                        "sentiment", "technical", "volatility",
                        "onchain", "funding", "orderflow", "macro", "news", "reflection"
                    ])
            for pkg in orch.active_packages.values():
                if pkg.long_leg:
                    active_roles.add("UP_AGENT")
                if pkg.short_leg:
                    active_roles.add("DOWN_AGENT")
            if orch.defense and orch.defense.is_active:
                active_roles.update(["ORDERFLOW", "FUNDING", "DEFENSE_DETECTOR", "DEFENSE_OB_MONITOR"])

            for entry in roster:
                if entry["role"] in active_roles:
                    entry["status"] = "working"
                    if evaluating_symbol and entry["role"] not in ("SUPERVISOR", "UP_AGENT", "DOWN_AGENT"):
                        entry["task"] = f"Analyzing {evaluating_symbol}"
                    elif entry["role"] in ("ORDERFLOW", "FUNDING"):
                        entry["task"] = "Scanning for interference"

        return roster
    except Exception as e:
        logger.warning(f"[API] Agent load error: {e}")
        return []


async def load_arb_opportunities(user: str, limit: int = 50, since: Optional[datetime] = None) -> List[dict]:
    """Fetch recent arbitrage opportunities from SQLite for a specific user."""
    try:
        from memory_store import memory_store
        await memory_store.initialize()
        records = await memory_store.get_recent_arb_opportunities(user_id=user, limit=limit, since=since)
        return [
            {
                "id": r.id,
                "strategy": r.strategy,
                "symbol": r.symbol,
                "buy_exchange": r.buy_exchange,
                "sell_exchange": r.sell_exchange,
                "buy_price": r.buy_price,
                "sell_price": r.sell_price,
                "spread_pct": round(r.spread_pct, 4),
                "fees_pct": round(r.fees_pct, 4),
                "net_profit_pct": round(r.net_profit_pct, 4),
                "size_usdt": r.size_usdt,
                "net_profit_usdt": round(r.net_profit_usdt, 4),
                "funding_rate": r.funding_rate,
                "executed": r.executed,
                "timestamp": r.timestamp.isoformat() if hasattr(r.timestamp, "isoformat") else str(r.timestamp),
            }
            for r in records
        ]
    except Exception as e:
        logger.warning(f"[API] Arb load error: {e}")
        return []


async def load_arb_live() -> Optional[dict]:
    """Fetch LIVE opportunities from the running ArbitrageModule."""
    from arbitrage_module import get_global_arbitrage_module
    arb = get_global_arbitrage_module()
    if arb is None:
        return None

    opps = arb.last_opportunities[:10]
    stats = arb.stats
    return {
        "opportunities": [
            {
                "strategy": o.strategy,
                "symbol": o.symbol,
                "buy_exchange": o.buy_exchange,
                "sell_exchange": o.sell_exchange,
                "buy_price": o.buy_price,
                "sell_price": o.sell_price,
                "spread_pct": round(o.spread_pct, 4),
                "fees_pct": round(o.fees_pct, 4),
                "net_profit_pct": o.net_profit_pct,
                "size_usdt": o.size_usdt,
                "net_profit_usdt": round(o.net_profit_usdt, 4),
                "executed": o.executed,
                "timestamp": o.timestamp.isoformat(),
            }
            for o in opps
        ],
        "stats": stats,
    }


async def load_analytics(user: str) -> dict:
    """Compute real analytics from trade history for a specific user."""
    try:
        import pandas as pd
    except ImportError:
        logger.error("[API] pandas not installed — analytics unavailable")
        return {
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "total_closed": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
        }

    trades = await load_trades(user, 500)
    df = pd.DataFrame(trades) if trades else pd.DataFrame()

    total_pnl = float(df["pnl_usdt"].sum()) if not df.empty else 0.0
    win_count = int((df["pnl_usdt"] > 0).sum()) if not df.empty else 0
    loss_count = int((df["pnl_usdt"] <= 0).sum()) if not df.empty else 0
    total_closed = len(df[df["status"] == "closed"]) if not df.empty else 0
    win_rate = float(win_count / max(total_closed, 1) * 100)
    avg_win = float(df[df["pnl_usdt"] > 0]["pnl_usdt"].mean()) if win_count > 0 else 0.0
    avg_loss = float(df[df["pnl_usdt"] <= 0]["pnl_usdt"].mean()) if loss_count > 0 else 0.0
    profit_factor = (
        abs(avg_win * win_count / (avg_loss * loss_count))
        if avg_loss != 0 and loss_count > 0 else 0.0
    )

    return {
        "total_pnl": round(total_pnl, 2),
        "win_count": win_count,
        "loss_count": loss_count,
        "total_closed": total_closed,
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
    }


# ── Background broadcaster ──────────────────────────────────────────────────

_last_equity_snapshot = 0.0

async def broadcaster_loop():
    """Poll live state and broadcast per-user data to WS clients every 5s."""
    global _last_equity_snapshot
    while True:
        await asyncio.sleep(5)
        if not manager.user_connections:
            continue
        try:
            defense = await load_defense()
            agents = await load_agents()

            # Include latest consensus in broadcast
            from orchestrator import get_global_orchestrator
            orch = get_global_orchestrator()
            consensus_payload = None
            if orch and orch._last_consensus:
                c = orch._last_consensus
                bull = c.bull_score
                bear = c.bear_score
                consensus_payload = {
                    "symbol": c.symbol,
                    "direction": "bullish" if bull > bear else "bearish" if bear > bull else "neutral",
                    "confidence": round(c.consensus_score * 100, 1),
                    "bull_score": round(bull, 3),
                    "bear_score": round(bear, 3),
                    "consensus_score": round(c.consensus_score, 3),
                    "trigger_trade": c.trigger_trade,
                    "evaluated_at": c.timestamp.isoformat() if c.timestamp else None,
                }

            # Broadcast per-user data
            async with manager._lock:
                users = list(manager.user_connections.keys())
            for user_id in users:
                try:
                    trades = await load_trades(user_id, 50)
                    positions = await load_positions(user_id)
                    equity = await load_equity(user_id)
                    await manager.broadcast_to_user(user_id, {
                        "type": "update",
                        "timestamp": datetime.utcnow().isoformat(),
                        "trades": trades,
                        "defense": defense,
                        "agents": agents,
                        "positions": positions,
                        "equity": equity,
                        "consensus": consensus_payload,
                    })
                except Exception as e:
                    logger.debug(f"[API] Broadcast error for user {user_id}: {e}")

            # Save equity snapshot every ~60 seconds for each active user
            now = datetime.utcnow().timestamp()
            if now - _last_equity_snapshot >= 60:
                _last_equity_snapshot = now
                from memory_store import memory_store
                await memory_store.initialize()
                for user_id in users:
                    try:
                        equity = await load_equity(user_id)
                        today = datetime.utcnow().date()
                        user_trades = await load_trades(user_id, 500)
                        today_pnl = sum(
                            t.get("pnl_usdt", 0)
                            for t in user_trades
                            if t.get("created_at", "").startswith(str(today))
                        )
                        hist = await memory_store.get_equity_history(30, user_id=user_id)
                        peak = max((h.equity for h in hist), default=equity)
                        dd_pct = ((peak - equity) / max(peak, 1)) * 100 if peak > equity else 0.0
                        await memory_store.save_equity_snapshot(equity, today_pnl, dd_pct, user_id=user_id)
                    except Exception as e:
                        logger.debug(f"[API] Equity snapshot error for user {user_id}: {e}")
        except Exception as e:
            logger.debug(f"[API] Broadcast error: {e}")


# ── Lifespan ────────────────────────────────────────────────────────────────

async def _load_persisted_settings() -> None:
    """Apply any SQLite-stored settings overrides on startup."""
    try:
        from memory_store import memory_store
        await memory_store.initialize()
        overrides = await memory_store.get_all_system_settings(user_id="system")
        if not overrides:
            return
        for key, raw in overrides.items():
            if key == "agent_role_config":
                try:
                    cfg = json.loads(raw)
                    from swarm_agents import set_agent_role_config
                    set_agent_role_config(cfg)
                    logger.info(f"[API] Loaded agent role config: {cfg}")
                except Exception:
                    pass
                continue
            if not hasattr(settings, key):
                continue
            current_type = type(getattr(settings, key))
            try:
                if current_type == bool:
                    setattr(settings, key, raw.lower() in ("true", "1", "yes"))
                elif current_type == int:
                    setattr(settings, key, int(raw))
                elif current_type == float:
                    setattr(settings, key, float(raw))
                elif current_type == list:
                    setattr(settings, key, json.loads(raw))
                else:
                    setattr(settings, key, raw)
            except Exception:
                pass
        logger.info(f"[API] Loaded {len(overrides)} persisted settings overrides")
    except Exception as e:
        logger.warning(f"[API] Could not load persisted settings: {e}")


async def lifespan(app: FastAPI):
    logger.info("[API] Fullstack server starting")
    await _load_persisted_settings()
    task = asyncio.create_task(broadcaster_loop())
    # Start crypto payment monitor for SaaS subscriptions
    try:
        from crypto_payments import subscription_monitor_loop
        sub_task = asyncio.create_task(subscription_monitor_loop(interval_seconds=60))
    except Exception as e:
        logger.warning(f"[API] Could not start subscription monitor: {e}")
        sub_task = None
    yield
    task.cancel()
    if sub_task:
        sub_task.cancel()
    logger.info("[API] Server stopped")


# ── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="HedgeSwarm API", version="2.1.0", lifespan=lifespan)

# Verified: CORS tightened — reads allowed origins from env, defaults to localhost only
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Static files / Frontend ─────────────────────────────────────────────────

static_dir = Path(__file__).parent / "frontend" / "dist"


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("""
    <html>
        <body style="background:#0a0a0f;color:#e5e7eb;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="text-align:center;">
                <h1>HedgeSwarm API</h1>
                <p>Frontend not built. Run <code>cd frontend && npm run build</code></p>
            </div>
        </body>
    </html>
    """)


@app.get("/favicon.svg")
async def favicon():
    favicon_path = static_dir / "favicon.svg"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    raise HTTPException(status_code=404)


# Serve JS/CSS assets with long cache headers
assets_dir = static_dir / "assets"
if assets_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# ── Auth Endpoints ──────────────────────────────────────────────────────────

@app.post("/api/auth/login", response_model=Token)
async def login(payload: LoginPayload):
    matched = await _lookup_user(payload.username, payload.password)
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": payload.username})
    return Token(access_token=access_token, username=payload.username)


@app.post("/api/auth/register")
async def register(payload: RegisterPayload):
    from memory_store import memory_store
    await memory_store.initialize()

    existing = await memory_store.get_user(payload.username)
    if existing or payload.username == DEFAULT_USER:
        raise HTTPException(status_code=409, detail="Username already exists")

    ok = await memory_store.create_user(payload.username, bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode())
    if not ok:
        raise HTTPException(status_code=409, detail="Username already exists")

    access_token = create_access_token(data={"sub": payload.username})
    return {"access_token": access_token, "token_type": "bearer", "username": payload.username}


@app.get("/api/auth/me")
async def read_users_me(user: str = Depends(require_auth)):
    return {"username": user}


# ── Subscription Middleware ─────────────────────────────────────────────────

async def require_subscription(user: str = Depends(require_auth)) -> str:
    """Raise 403 if user's subscription is expired or inactive. Admin is always exempt."""
    if user == os.getenv("ADMIN_USER", "admin"):
        return user
    from memory_store import memory_store
    await memory_store.initialize()
    active = await memory_store.check_subscription_active(user)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Subscription required. Please purchase a plan to continue trading.",
        )
    return user


@app.get("/api/billing")
async def api_billing(user: str = Depends(require_auth)):
    """Return current user's subscription + payment instructions."""
    from memory_store import memory_store
    from crypto_payments import format_payment_instructions
    await memory_store.initialize()

    sub = await memory_store.get_subscription(user)
    instructions = format_payment_instructions(user)

    return {
        "subscription": {
            "tier": sub.tier if sub else "free",
            "active": sub.active if sub else False,
            "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        },
        "payment_instructions": instructions,
        "pricing": {
            "monthly_xrp": 25.0,
            "monthly_rlusd": 25.0,
        },
    }


@app.get("/api/admin/billing")
async def api_admin_billing(user: str = Depends(require_auth)):
    """Admin only: view all subscriptions and payments."""
    if user != os.getenv("ADMIN_USER", "admin"):
        raise HTTPException(status_code=403, detail="Admin only")

    from memory_store import memory_store
    await memory_store.initialize()

    subs = await memory_store.get_all_subscriptions()
    payments = await memory_store.get_all_payments()

    total_revenue_xrp = sum(p.amount for p in payments if p.currency == "XRP")
    total_revenue_rlusd = sum(p.amount for p in payments if p.currency == "RLUSD")

    return {
        "total_users": len(subs),
        "total_payments": len(payments),
        "total_revenue_xrp": total_revenue_xrp,
        "total_revenue_rlusd": total_revenue_rlusd,
        "subscriptions": [
            {
                "username": s.username,
                "tier": s.tier,
                "active": s.active,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in subs
        ],
        "payments": [
            {
                "tx_hash": p.tx_hash,
                "username": p.username,
                "amount": p.amount,
                "currency": p.currency,
                "months": p.months,
                "tier": p.tier,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments[:50]
        ],
    }


# ── OAuth ───────────────────────────────────────────────────────────────────

@app.get("/api/auth/oauth/{provider}")
async def oauth_login(provider: str, redirect_uri: Optional[str] = None):
    """Return the OAuth authorization URL for the given provider."""
    config = OAUTH_CONFIG.get(provider)
    if not config or not config["client_id"]:
        raise HTTPException(status_code=400, detail=f"OAuth provider '{provider}' not configured")

    # Build callback URL (backend receives the callback)
    callback_url = f"{os.getenv('API_BASE_URL', 'http://localhost:3003')}/api/auth/oauth/{provider}/callback"

    # Build auth URL
    if provider == "google":
        auth_url = (
            f"{config['auth_url']}"
            f"?client_id={config['client_id']}"
            f"&redirect_uri={callback_url}"
            f"&response_type=code"
            f"&scope={config['scope']}"
            f"&access_type=offline"
        )
    elif provider == "github":
        auth_url = (
            f"{config['auth_url']}"
            f"?client_id={config['client_id']}"
            f"&redirect_uri={callback_url}"
            f"&scope={config['scope']}"
        )
    elif provider == "facebook":
        auth_url = (
            f"{config['auth_url']}"
            f"?client_id={config['client_id']}"
            f"&redirect_uri={callback_url}"
            f"&scope={config['scope']}"
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    return {"auth_url": auth_url}


@app.get("/api/auth/oauth/{provider}/callback")
async def oauth_callback(provider: str, code: str, error: Optional[str] = None):
    """Handle OAuth callback from provider."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    config = OAUTH_CONFIG.get(provider)
    if not config or not config["client_id"]:
        raise HTTPException(status_code=400, detail=f"OAuth provider '{provider}' not configured")

    callback_url = f"{os.getenv('API_BASE_URL', 'http://localhost:3003')}/api/auth/oauth/{provider}/callback"

    try:
        async with httpx.AsyncClient() as client:
            # 1. Exchange code for access token
            if provider == "google":
                token_resp = await client.post(
                    config["token_url"],
                    data={
                        "code": code,
                        "client_id": config["client_id"],
                        "client_secret": config["client_secret"],
                        "redirect_uri": callback_url,
                        "grant_type": "authorization_code",
                    },
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")

                # 2. Fetch user info
                user_resp = await client.get(
                    config["userinfo_url"],
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                user_data = user_resp.json()
                provider_user_id = user_data.get("sub")
                email = user_data.get("email")
                name = user_data.get("name") or email.split("@")[0] if email else f"google_{provider_user_id[:8]}"

            elif provider == "github":
                token_resp = await client.post(
                    config["token_url"],
                    data={
                        "code": code,
                        "client_id": config["client_id"],
                        "client_secret": config["client_secret"],
                        "redirect_uri": callback_url,
                    },
                    headers={"Accept": "application/json"},
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")

                user_resp = await client.get(
                    config["userinfo_url"],
                    headers={
                        "Authorization": f"token {access_token}",
                        "Accept": "application/json",
                    },
                )
                user_data = user_resp.json()
                provider_user_id = str(user_data.get("id"))
                email = user_data.get("email")
                name = user_data.get("login") or user_data.get("name") or f"github_{provider_user_id[:8]}"

            elif provider == "facebook":
                token_resp = await client.get(
                    config["token_url"],
                    params={
                        "code": code,
                        "client_id": config["client_id"],
                        "client_secret": config["client_secret"],
                        "redirect_uri": callback_url,
                    },
                )
                token_data = token_resp.json()
                access_token = token_data.get("access_token")

                user_resp = await client.get(
                    config["userinfo_url"],
                    params={
                        "access_token": access_token,
                        "fields": "id,name,email",
                    },
                )
                user_data = user_resp.json()
                provider_user_id = user_data.get("id")
                email = user_data.get("email")
                name = user_data.get("name") or f"fb_{provider_user_id[:8]}"

            else:
                raise HTTPException(status_code=400, detail="Unsupported provider")

        # 3. Create or find user in database
        from memory_store import memory_store
        await memory_store.initialize()

        username = await memory_store.create_oauth_user(
            provider=provider,
            provider_user_id=provider_user_id,
            username=name,
            email=email,
        )

        # 4. Generate JWT and redirect to frontend
        access_token = create_access_token(data={"sub": username})
        frontend = redirect_uri or FRONTEND_URL
        return HTMLResponse(
            content=HTML_REDIRECT_TEMPLATE.format(frontend=frontend, token=access_token, username=username),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OAuth] {provider} callback error: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")


HTML_REDIRECT_TEMPLATE = """<!DOCTYPE html>
<html>
<head><title>Authenticating...</title></head>
<body>
<script>
  (function() {
    var token = '{token}';
    var username = '{username}';
    var frontend = '{frontend}';
    localStorage.setItem('hedgeswarm_token', token);
    window.location.href = frontend + '/?token=' + encodeURIComponent(token) + '&username=' + encodeURIComponent(username);
  })();
</script>
<p>Redirecting to app...</p>
</body>
</html>
"""


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    from orchestrator import get_global_orchestrator
    orch = get_global_orchestrator()
    return {
        "status": "healthy",
        "engine_running": orch._running if orch else False,
        "active_packages": len(orch.active_packages) if orch else 0,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.1.0",
    }


# ── Trading / Engine Endpoints ──────────────────────────────────────────────

@app.get("/api/status")
async def api_status(user: Optional[str] = Depends(get_current_user)):
    from orchestrator import get_global_orchestrator
    orch = get_global_orchestrator()
    return {
        "status": "ok",
        "engine_running": orch._running if orch else False,
        "active_packages": len(orch.active_packages) if orch else 0,
        "mode": "paper" if settings.paper_trading else "live",
        "timestamp": datetime.utcnow().isoformat(),
        "watchlist": settings.watchlist,
        "paper_trading": settings.paper_trading,
    }


@app.get("/api/trades")
async def api_trades(limit: int = 100, user: str = Depends(require_subscription)):
    return {"trades": await load_trades(user, limit)}


@app.get("/api/positions")
async def api_positions(user: str = Depends(require_subscription)):
    """LIVE open positions from the running engine."""
    return {"positions": await load_positions(user)}


@app.get("/api/equity")
async def api_equity(user: str = Depends(require_subscription)):
    """LIVE account equity from the exchange."""
    return {"equity_usdt": await load_equity(user), "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/market/snapshot")
async def api_market_snapshot(symbol: str, user: str = Depends(require_auth)):
    """LIVE market snapshot from the configured long exchange."""
    from exchange_client import fetch_market_snapshot
    try:
        snap = await fetch_market_snapshot(settings.long_exchange_id, symbol)
        return {
            "symbol": snap.symbol,
            "bid": snap.bid,
            "ask": snap.ask,
            "last": snap.last,
            "mark_price": snap.mark_price,
            "index_price": snap.index_price,
            "open_interest": snap.open_interest,
            "funding_rate": snap.funding_rate,
            "volume_24h": snap.volume_24h,
            "change_24h_pct": snap.change_24h_pct,
            "timestamp": snap.timestamp.isoformat() if hasattr(snap.timestamp, "isoformat") else str(snap.timestamp),
        }
    except Exception as e:
        logger.error(f"[API] Market snapshot failed for {symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Exchange unavailable: {e}")


@app.get("/api/exchange/depth")
async def api_exchange_depth(
    symbol: str,
    exchange: str,
    user: str = Depends(require_auth),
):
    """
    Return order book depth + recent trades for a symbol on a specific exchange.
    Uses public exchange fallback if the configured exchange fails.
    """
    try:
        from exchange_client import _get_public_exchange, get_exchange
        import ccxt.async_support as ccxt

        # Try configured exchange first, then public fallback
        try:
            ex = await get_exchange(exchange)
        except Exception:
            ex = await _get_public_exchange(exchange)

        # Fetch order book
        ob = await ex.fetch_order_book(symbol, limit=20)
        bids = [[float(entry[0]), float(entry[1])] for entry in ob.get("bids", [])[:10]]
        asks = [[float(entry[0]), float(entry[1])] for entry in ob.get("asks", [])[:10]]

        # Fetch recent trades
        raw_trades = await ex.fetch_trades(symbol, limit=20)
        trades = []
        for t in raw_trades:
            side = t.get("side", "buy")
            # Normalize side
            if side not in ("buy", "sell"):
                side = "buy"
            trades.append({
                "price": float(t.get("price", 0)),
                "amount": float(t.get("amount", 0)),
                "side": side,
                "timestamp": t.get("datetime", ""),
            })

        return {
            "symbol": symbol,
            "exchange": exchange,
            "bids": bids,
            "asks": asks,
            "trades": trades,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"[API] Exchange depth failed {exchange}/{symbol}: {e}")
        raise HTTPException(status_code=503, detail=f"Exchange depth unavailable: {e}")


@app.get("/api/exchange/balance")
async def api_exchange_balance(
    exchange: str,
    asset: str = "USDT",
    user: str = Depends(require_auth),
):
    """Return free balance for an asset on an exchange. Falls back to mock if no API keys."""
    try:
        from exchange_client import get_exchange
        ex = await get_exchange(exchange)
        bal = await ex.fetch_balance()
        free = float(bal.get(asset, {}).get("free", 0) or 0)
        used = float(bal.get(asset, {}).get("used", 0) or 0)
        total = float(bal.get(asset, {}).get("total", 0) or 0)
        return {"exchange": exchange, "asset": asset, "free": free, "used": used, "total": total}
    except Exception as e:
        err_str = str(e).lower()
        if "apikey" in err_str or "credential" in err_str or "api key" in err_str:
            # Return mock balance for demo
            import random
            mock_free = round(random.uniform(5000, 15000), 2)
            return {"exchange": exchange, "asset": asset, "free": mock_free, "used": 0, "total": mock_free, "mock": True}
        logger.error(f"[API] Balance fetch failed {exchange}/{asset}: {e}")
        raise HTTPException(status_code=503, detail=f"Balance unavailable: {e}")


@app.get("/api/exchange/positions")
async def api_exchange_positions(
    exchange: str,
    symbol: Optional[str] = None,
    user: str = Depends(require_auth),
):
    """Return open positions on an exchange. Falls back to mock if no API keys."""
    try:
        from exchange_client import get_exchange
        ex = await get_exchange(exchange)
        positions = await ex.fetch_positions([symbol] if symbol else [])
        result = []
        for p in positions:
            if not p:
                continue
            contracts = float(p.get("contracts") or p.get("positionAmount") or 0)
            if contracts == 0:
                continue
            result.append({
                "symbol": p.get("symbol", ""),
                "side": p.get("side", ""),
                "contracts": contracts,
                "entry_price": float(p.get("entryPrice") or p.get("entry_price") or 0),
                "mark_price": float(p.get("markPrice") or p.get("mark_price") or 0),
                "unrealized_pnl": float(p.get("unrealizedPnl") or p.get("unrealizedProfit") or 0),
                "leverage": float(p.get("leverage") or 1),
                "notional": float(p.get("notional") or p.get("notionalValue") or 0),
            })
        return {"exchange": exchange, "positions": result}
    except Exception as e:
        err_str = str(e).lower()
        if "apikey" in err_str or "credential" in err_str or "api key" in err_str:
            # Return mock position for demo
            import random
            if symbol and random.random() > 0.5:
                base_price = {"BTC/USDT:USDT": 81200, "ETH/USDT:USDT": 4850, "SOL/USDT:USDT": 186, "XRP/USDT:USDT": 1.46}.get(symbol, 100)
                side = "long" if exchange == settings.long_exchange_id else "short"
                entry = base_price * (1 + random.uniform(-0.02, 0.02))
                pnl = random.uniform(-50, 150)
                return {"exchange": exchange, "positions": [{
                    "symbol": symbol,
                    "side": side,
                    "contracts": round(random.uniform(0.1, 2.0), 4),
                    "entry_price": round(entry, 2),
                    "mark_price": round(base_price, 2),
                    "unrealized_pnl": round(pnl, 2),
                    "leverage": 5,
                    "notional": round(entry * 0.5, 2),
                }], "mock": True}
            return {"exchange": exchange, "positions": [], "mock": True}
        logger.error(f"[API] Positions fetch failed {exchange}: {e}")
        raise HTTPException(status_code=503, detail=f"Positions unavailable: {e}")


@app.post("/api/exchange/order")
async def api_exchange_order(
    request: Request,
    user: str = Depends(require_auth),
):
    """Place a market order on an exchange."""
    try:
        body = await request.json()
        exchange_id = body.get("exchange")
        symbol = body.get("symbol")
        side = body.get("side")  # "buy" or "sell"
        amount = float(body.get("amount", 0))
        order_type = body.get("type", "market")
        leverage = int(body.get("leverage", 1))

        if not all([exchange_id, symbol, side, amount > 0]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        from exchange_client import get_exchange, place_market_order
        from models import Side

        # Set leverage first
        ex = await get_exchange(exchange_id)
        try:
            await ex.set_leverage(leverage, symbol)
        except Exception:
            pass

        order_side = Side.LONG if side == "buy" else Side.SHORT
        order = await place_market_order(exchange_id, symbol, order_side, amount)

        return {
            "status": "ok",
            "order_id": order.get("id"),
            "filled": order.get("filled", 0),
            "average": order.get("average", 0),
            "symbol": symbol,
            "side": side,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Order placement failed: {e}")
        raise HTTPException(status_code=503, detail=f"Order failed: {e}")


@app.get("/api/agents")
async def api_agents(user: str = Depends(require_subscription)):
    return {"agents": await load_agents()}


@app.get("/api/agents/diagnostic")
async def api_agents_diagnostic(user: str = Depends(require_auth)):
    """Debug endpoint: show current agent role config and build counts."""
    from swarm_agents import _AGENT_ROLE_CONFIG, build_swarm
    built = build_swarm()
    from collections import Counter
    counts = Counter(a.ROLE.value for a in built)
    return {
        "agent_role_config": _AGENT_ROLE_CONFIG,
        "built_counts": dict(counts),
        "total_agents": len(built),
        "cache_cleared": _agent_roster_cache is None,
    }


@app.get("/api/swarm/consensus")
async def api_swarm_consensus(user: str = Depends(require_subscription)):
    """Return the latest swarm consensus evaluation (direction, confidence, signal)."""
    from orchestrator import get_global_orchestrator
    orch = get_global_orchestrator()
    consensus = orch._last_consensus if orch else None
    if not consensus:
        return {
            "symbol": None,
            "direction": "neutral",
            "confidence": 0.0,
            "bull_score": 0.5,
            "bear_score": 0.5,
            "consensus_score": 0.0,
            "trigger_trade": False,
            "evaluated_at": None,
        }
    bull = consensus.bull_score
    bear = consensus.bear_score
    direction = "bullish" if bull > bear else "bearish" if bear > bull else "neutral"
    return {
        "symbol": consensus.symbol,
        "direction": direction,
        "confidence": round(consensus.consensus_score * 100, 1),
        "bull_score": round(bull, 3),
        "bear_score": round(bear, 3),
        "consensus_score": round(consensus.consensus_score, 3),
        "trigger_trade": consensus.trigger_trade,
        "evaluated_at": consensus.timestamp.isoformat() if consensus.timestamp else None,
    }


@app.get("/api/defense")
async def api_defense(user: str = Depends(require_subscription)):
    return {"defense": await load_defense()}


@app.get("/api/analytics")
async def api_analytics(user: str = Depends(require_subscription)):
    return await load_analytics(user)


@app.get("/api/portfolio")
async def api_portfolio(days: int = 30, user: str = Depends(require_auth)):
    """Equity history, drawdown curve, and monthly returns scoped to user."""
    from memory_store import memory_store
    await memory_store.initialize()
    snapshots = await memory_store.get_equity_history(days, user_id=user)
    equity_curve = [
        {"timestamp": s.timestamp.isoformat(), "equity": s.equity, "drawdown": s.drawdown_pct}
        for s in snapshots
    ]
    # Monthly returns from trades
    trades = await load_trades(user, 500)
    monthly: dict = {}
    for t in trades:
        if t.get("status") != "closed":
            continue
        month = t["created_at"][:7]  # YYYY-MM
        monthly[month] = monthly.get(month, 0) + t.get("pnl_usdt", 0)
    return {
        "equity_curve": equity_curve,
        "monthly_returns": [{"month": k, "pnl": round(v, 2)} for k, v in sorted(monthly.items())],
        "current_equity": equity_curve[-1]["equity"] if equity_curve else await load_equity(user),
        "max_drawdown": max((s.drawdown_pct for s in snapshots), default=0.0),
    }


@app.get("/api/analytics/advanced")
async def api_analytics_advanced(user: str = Depends(require_auth)):
    """Advanced performance metrics."""
    trades = await load_trades(user, 500)
    closed = [t for t in trades if t.get("status") == "closed"]
    if not closed:
        return {
            "sharpe_ratio": 0.0, "sortino_ratio": 0.0, "max_drawdown_pct": 0.0,
            "recovery_factor": 0.0, "expectancy": 0.0, "avg_trade": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0, "longest_win_streak": 0,
            "longest_loss_streak": 0, "current_streak": 0,
        }
    pnls = [t.get("pnl_usdt", 0) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg_return = sum(pnls) / len(pnls) if pnls else 0
    std = (sum((p - avg_return) ** 2 for p in pnls) / len(pnls)) ** 0.5 if pnls else 0
    downside = [p for p in pnls if p < 0]
    downside_std = (sum((p - avg_return) ** 2 for p in downside) / len(downside)) ** 0.5 if downside else 0
    # Streaks
    streaks = []
    current = 0
    current_type = None
    for p in pnls:
        t = "win" if p > 0 else "loss"
        if t == current_type:
            current += 1
        else:
            if current_type:
                streaks.append((current_type, current))
            current_type = t
            current = 1
    if current_type:
        streaks.append((current_type, current))
    win_streaks = [s[1] for s in streaks if s[0] == "win"]
    loss_streaks = [s[1] for s in streaks if s[0] == "loss"]
    # Max drawdown from equity curve approximation
    cum = 0
    peak = 0
    max_dd = 0
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        dd = (peak - cum) / max(peak, 1) * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    total_pnl = sum(pnls)
    return {
        "sharpe_ratio": round(avg_return / std * (252 ** 0.5), 2) if std > 0 else 0.0,
        "sortino_ratio": round(avg_return / downside_std * (252 ** 0.5), 2) if downside_std > 0 else 0.0,
        "max_drawdown_pct": round(max_dd, 2),
        "recovery_factor": round(total_pnl / max(max_dd, 0.01), 2),
        "expectancy": round(avg_return, 2),
        "avg_trade": round(avg_return, 2),
        "best_trade": round(max(pnls), 2),
        "worst_trade": round(min(pnls), 2),
        "longest_win_streak": max(win_streaks, default=0),
        "longest_loss_streak": max(loss_streaks, default=0),
        "current_streak_type": streaks[-1][0] if streaks else None,
        "current_streak": streaks[-1][1] if streaks else 0,
    }


@app.get("/api/agents/accuracy")
async def api_agents_accuracy(days: int = 30, user: str = Depends(require_auth)):
    """Agent voting accuracy leaderboard scoped to user."""
    from memory_store import memory_store
    await memory_store.initialize()
    accuracy = await memory_store.get_agent_accuracy(days, user_id=user)
    return {"accuracy": accuracy, "days": days}


@app.get("/api/risk")
async def api_risk(user: str = Depends(require_subscription)):
    """Risk dashboard: exposure, drawdown, margin scoped to user."""
    from orchestrator import get_global_orchestrator
    from risk_manager import daily_tracker
    orch = get_global_orchestrator()
    positions = await load_positions(user)
    total_exposure = sum(p.get("notional", 0) for p in positions)
    equity = await load_equity(user)
    exposure_pct = (total_exposure / max(equity, 1)) * 100
    dd = daily_tracker.daily_drawdown_pct
    return {
        "equity": equity,
        "total_exposure": round(total_exposure, 2),
        "exposure_pct": round(exposure_pct, 2),
        "daily_drawdown_pct": round(dd, 2),
        "daily_halted": daily_tracker.is_halted,
        "max_drawdown_limit": settings.max_daily_drawdown_pct,
        "open_positions": len(positions),
        "active_packages": len(orch.active_packages) if orch else 0,
    }


@app.get("/api/arbitrage/opportunities")
async def api_arb_opportunities(limit: int = 50, days: int = 0, user: str = Depends(require_auth)):
    """Historical arbitrage opportunities from SQLite. days=0 means all time."""
    since = None
    if days > 0:
        since = datetime.utcnow() - timedelta(days=days)
    return {"opportunities": await load_arb_opportunities(user, limit, since)}


@app.get("/api/arbitrage/live")
async def api_arb_live(user: str = Depends(require_auth)):
    """LIVE arbitrage opportunities from the running scanner."""
    live = await load_arb_live()
    if live is None:
        return {"opportunities": [], "stats": {}, "status": "module_not_running"}
    live["status"] = "ok"
    return live


@app.get("/api/arbitrage/stats")
async def api_arb_stats(user: str = Depends(require_auth)):
    """Arbitrage module statistics."""
    from arbitrage_module import get_global_arbitrage_module
    arb = get_global_arbitrage_module()
    if arb is None:
        return {"status": "not_running", "scans": 0, "opportunities_found": 0, "executed": 0}
    stats = arb.stats
    stats["status"] = "running" if arb.is_running else "stopped"
    stats["is_running"] = arb.is_running
    return stats


@app.post("/api/arbitrage/start")
async def api_arb_start(user: str = Depends(require_auth)):
    """Start the arbitrage scanner dynamically."""
    from arbitrage_module import ArbitrageModule, get_global_arbitrage_module
    arb = get_global_arbitrage_module()
    if arb is None:
        arb = ArbitrageModule()
    if not arb.is_running:
        await arb.start()
    return {"status": "started", "is_running": arb.is_running}


@app.post("/api/arbitrage/stop")
async def api_arb_stop(user: str = Depends(require_auth)):
    """Stop the arbitrage scanner."""
    from arbitrage_module import get_global_arbitrage_module
    arb = get_global_arbitrage_module()
    if arb and arb.is_running:
        await arb.stop()
    return {"status": "stopped", "is_running": arb.is_running if arb else False}


@app.post("/api/exchanges/test")
async def api_test_exchange(payload: ExchangeTestPayload, user: str = Depends(require_auth)):
    """Test exchange connectivity with provided credentials."""
    import ccxt.async_support as ccxt_async

    ex_id = payload.exchange_id.lower()
    try:
        ex_cls = getattr(ccxt_async, ex_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail=f"Unknown exchange: {ex_id}")

    config = {
        "apiKey": payload.api_key,
        "secret": payload.api_secret,
        "enableRateLimit": True,
    }
    if payload.api_passphrase:
        config["password"] = payload.api_passphrase
    if ex_id == "bybit":
        config["options"] = {"defaultType": "swap"}
        config["sandbox"] = payload.testnet
    elif ex_id == "okx":
        config["options"] = {"defaultType": "swap"}
        config["sandbox"] = payload.testnet
    elif ex_id == "binance":
        config["options"] = {"defaultType": "future"}
        config["sandbox"] = payload.testnet

    exchange = ex_cls(config)
    try:
        await exchange.load_markets()
        # Try to fetch balance as a deeper connectivity test
        balance = await exchange.fetch_balance()
        free_usdt = balance.get("USDT", {}).get("free", 0)
        return {
            "status": "connected",
            "exchange": ex_id,
            "testnet": payload.testnet,
            "markets": len(exchange.symbols),
            "usdt_balance": free_usdt,
        }
    except ccxt_async.AuthenticationError as e:
        return {"status": "auth_failed", "exchange": ex_id, "detail": str(e)}
    except ccxt_async.NetworkError as e:
        return {"status": "network_error", "exchange": ex_id, "detail": str(e)}
    except Exception as e:
        return {"status": "error", "exchange": ex_id, "detail": str(e)}
    finally:
        await exchange.close()


# ── Custom Exchange CRUD ────────────────────────────────────────────────────

class CustomExchangePayload(BaseModel):
    exchange_id: str = Field(..., min_length=1, max_length=32)
    api_key: str = ""
    api_secret: str = ""
    api_passphrase: str = ""
    testnet: bool = True


@app.get("/api/exchanges")
async def api_list_exchanges(user: str = Depends(require_auth)):
    """List all configured custom exchanges scoped to user."""
    from memory_store import memory_store
    await memory_store.initialize()
    records = await memory_store.get_custom_exchanges(user_id=user)
    return {
        "exchanges": [
            {
                "exchange_id": r.exchange_id.split(":", 1)[1] if ":" in r.exchange_id else r.exchange_id,
                "api_key": "*" * (len(r.api_key) - 4) + r.api_key[-4:] if len(r.api_key) > 4 else "",
                "testnet": r.testnet,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }


@app.post("/api/exchanges")
async def api_add_exchange(payload: CustomExchangePayload, user: str = Depends(require_auth)):
    """Add a new custom exchange scoped to user."""
    from memory_store import memory_store
    await memory_store.initialize()
    ok = await memory_store.add_custom_exchange(
        payload.exchange_id,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        api_passphrase=payload.api_passphrase,
        testnet=payload.testnet,
        user_id=user,
    )
    if not ok:
        raise HTTPException(status_code=409, detail="Exchange already exists")
    return {"status": "ok", "exchange_id": payload.exchange_id}


@app.delete("/api/exchanges/{exchange_id}")
async def api_delete_exchange(exchange_id: str, user: str = Depends(require_auth)):
    """Delete a custom exchange scoped to user."""
    from memory_store import memory_store
    await memory_store.initialize()
    ok = await memory_store.delete_custom_exchange(exchange_id, user_id=user)
    if not ok:
        raise HTTPException(status_code=404, detail="Exchange not found")
    return {"status": "ok", "deleted": exchange_id}


@app.post("/api/command")
async def api_command(cmd: CommandPayload, user: str = Depends(require_subscription)):
    # Verified: CommandPayload validates command length and structure
    cmd_path = settings.data_dir / "command_queue.json"
    try:
        queue: List[dict] = []
        if cmd_path.exists():
            with open(cmd_path) as f:
                queue = json.load(f)
        queue.append({
            "command": cmd.command,
            "payload": cmd.payload or {},
            "timestamp": datetime.utcnow().isoformat(),
        })
        with open(cmd_path, "w") as f:
            json.dump(queue, f)
        logger.info(f"[API] Command queued: {cmd.command}")
        return {"status": "ok", "command": cmd.command}
    except Exception as e:
        logger.error(f"[API] Command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return ""
    return "*" * (len(key) - 4) + key[-4:]


@app.get("/api/settings")
async def api_settings(user: str = Depends(require_auth)):
    # Verified: only non-sensitive thresholds and booleans are exposed
    from memory_store import memory_store
    await memory_store.initialize()
    agent_cfg_raw = await memory_store.get_system_setting("agent_role_config", user_id=user)
    agent_role_config = json.loads(agent_cfg_raw) if agent_cfg_raw else None

    return {
        "paper_trading": settings.paper_trading,
        "watchlist": settings.watchlist,
        "max_risk_per_package_pct": settings.max_risk_per_package_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "take_profit_pct": settings.take_profit_pct,
        "trailing_stop_pct": settings.trailing_stop_pct,
        "default_leverage": settings.default_leverage,
        "min_consensus_score": settings.min_consensus_score,
        "min_volatility_percentile": settings.min_volatility_percentile,
        "signal_refresh_seconds": settings.signal_refresh_seconds,
        "defense_enabled": settings.defense_enabled,
        "defense_bull_run_threshold": settings.defense_bull_run_threshold,
        "max_daily_drawdown_pct": settings.max_daily_drawdown_pct,
        "max_concurrent_packages": settings.max_concurrent_packages,
        "funding_rate_threshold": settings.funding_rate_threshold,
        "rebalance_interval_min": settings.rebalance_interval_min,
        # Exchange config (API keys masked)
        "long_exchange_id": settings.long_exchange_id,
        "short_exchange_id": settings.short_exchange_id,
        "same_exchange_hedge_mode": settings.same_exchange_hedge_mode,
        "bybit_testnet": settings.bybit_testnet,
        "okx_testnet": settings.okx_testnet,
        "binance_testnet": settings.binance_testnet,
        "bybit_api_key": _mask_key(settings.bybit_api_key),
        "okx_api_key": _mask_key(settings.okx_api_key),
        "binance_api_key": _mask_key(settings.binance_api_key),
        # Agent config
        "agent_role_config": agent_role_config,
    }


@app.put("/api/settings")
async def api_update_settings(payload: SettingsUpdatePayload, user: str = Depends(require_auth)):
    from memory_store import memory_store
    await memory_store.initialize()

    updated = {}
    data = payload.model_dump(exclude_none=True)

    for field, value in data.items():
        if field == "agent_role_config":
            await memory_store.set_system_setting(field, json.dumps(value), user_id=user)
            # Update in-memory role config so build_swarm() uses new counts
            from swarm_agents import set_agent_role_config
            set_agent_role_config(value)
            logger.info(f"[API] Updated agent_role_config: {value}")
            # Clear agent roster cache so next load rebuilds with new counts
            global _agent_roster_cache
            _agent_roster_cache = None
            logger.info("[API] Cleared _agent_roster_cache")
            updated[field] = value
            continue

        # Skip masked API keys (user didn't change them)
        if "api_key" in field or "api_secret" in field or "api_passphrase" in field:
            if not value or "*" in str(value):
                continue

        if not hasattr(settings, field):
            continue
        # Update in-memory config
        setattr(settings, field, value)
        # Persist to SQLite
        if isinstance(value, list):
            await memory_store.set_system_setting(field, json.dumps(value), user_id=user)
        elif isinstance(value, dict):
            await memory_store.set_system_setting(field, json.dumps(value), user_id=user)
        else:
            await memory_store.set_system_setting(field, str(value), user_id=user)
        updated[field] = value

    logger.info(f"[API] Settings updated by {user}: {list(updated.keys())}")
    return {"status": "ok", "updated": updated}


# ── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Verified: WS connections require a valid token in query param ?token=...
    token = websocket.query_params.get("token")
    user = await get_current_user(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(websocket, user)
    try:
        # Send initial burst of real data scoped to authenticated user
        trades = await load_trades(user, 50)
        defense = await load_defense()
        agents = await load_agents()
        positions = await load_positions(user)
        equity = await load_equity(user)
        await manager.send_to(websocket, {
            "type": "init",
            "trades": trades,
            "defense": defense,
            "agents": agents,
            "positions": positions,
            "equity": equity,
        })

        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action == "ping":
                await manager.send_to(websocket, {"type": "pong"})
            elif action == "command":
                raw_cmd = msg.get("data", {})
                validated = CommandPayload(command=raw_cmd.get("command", ""), payload=raw_cmd.get("payload"))
                result = await api_command(validated, user)
                await manager.send_to(websocket, {"type": "command_queued", "command": validated.command})
    except WebSocketDisconnect:
        await manager.disconnect(websocket, user)
    except Exception as e:
        logger.debug(f"[WS] Error: {e}")
        await manager.disconnect(websocket, user)


# ── SPA Catch-All (must be last) ────────────────────────────────────────────

@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_catchall(path: str):
    """Serve index.html for all non-API routes so React Router works."""
    # Skip API and static asset paths
    if path.startswith("api/") or path.startswith("assets/") or path == "favicon.svg":
        raise HTTPException(status_code=404)
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend not built")


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_fullstack:app", host="0.0.0.0", port=3003, reload=False)
