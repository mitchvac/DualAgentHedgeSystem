"""
api_server.py
─────────────────────────────────────────────────────────────────────────────
FastAPI backend for the HedgeSwarm full-stack dashboard.

Provides:
  • REST API for trades, agents, defense status, analytics, settings
  • WebSocket /ws for real-time push updates
  • Serves the custom HTML dashboard from static/
  • Command endpoint for frontend → orchestrator control
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

import pandas as pd

from config import settings

# ── Connection Manager ──────────────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict) -> None:
        dead = []
        async with self._lock:
            connections = list(self.active_connections)
        for conn in connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        if dead:
            async with self._lock:
                for d in dead:
                    if d in self.active_connections:
                        self.active_connections.remove(d)

    async def send_to(self, websocket: WebSocket, message: dict) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)


manager = ConnectionManager()

# ── Data helpers ────────────────────────────────────────────────────────────

async def load_trades(limit: int = 100) -> List[dict]:
    from memory_store import memory_store
    await memory_store.initialize()
    records = await memory_store.get_recent_packages(limit)
    return [
        {
            "package_id": r.package_id[:8],
            "symbol": r.symbol,
            "status": r.status,
            "pnl_usdt": round(r.combined_pnl, 4),
            "risk_budget": round(r.risk_budget, 2),
            "pnl_pct": round(r.combined_pnl / max(r.risk_budget, 1) * 100, 2),
            "close_reason": r.close_reason,
            "created_at": r.created_at.isoformat() if hasattr(r.created_at, "isoformat") else str(r.created_at),
        }
        for r in records
    ]


async def load_defense() -> Optional[dict]:
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


async def load_agents() -> List[dict]:
    try:
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
        }
        return [
            {
                "agent_id": a.agent_id,
                "role": a.ROLE.value,
                "weight": a.VOTE_WEIGHT,
                "task": task_map.get(a.ROLE.value, "Standby"),
            }
            for a in agents
        ]
    except Exception as e:
        logger.warning(f"[API] Agent load error: {e}")
        return []


# ── Background broadcaster ──────────────────────────────────────────────────

async def broadcaster_loop():
    """Poll DB and broadcast updates to all WS clients every 5s."""
    while True:
        await asyncio.sleep(5)
        if not manager.active_connections:
            continue
        try:
            trades = await load_trades(50)
            defense = await load_defense()
            await manager.broadcast({
                "type": "update",
                "timestamp": datetime.utcnow().isoformat(),
                "trades": trades,
                "defense": defense,
            })
        except Exception as e:
            logger.debug(f"[API] Broadcast error: {e}")


# ── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[API] Server starting")
    task = asyncio.create_task(broadcaster_loop())
    yield
    task.cancel()
    logger.info("[API] Server stopped")


# ── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="HedgeSwarm API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure static dir exists
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ── HTML Dashboard ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Dashboard not built yet. Run the build step.</h1>")


# ── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return {
        "status": "ok",
        "mode": "paper" if settings.paper_trading else "live",
        "timestamp": datetime.utcnow().isoformat(),
        "watchlist": settings.watchlist,
        "paper_trading": settings.paper_trading,
    }


@app.get("/api/trades")
async def api_trades(limit: int = 100):
    return {"trades": await load_trades(limit)}


@app.get("/api/agents")
async def api_agents():
    return {"agents": await load_agents()}


@app.get("/api/defense")
async def api_defense():
    return {"defense": await load_defense()}


@app.get("/api/analytics")
async def api_analytics():
    trades = await load_trades(200)
    df = pd.DataFrame(trades) if trades else pd.DataFrame()

    total_pnl = df["pnl_usdt"].sum() if not df.empty else 0.0
    win_count = (df["pnl_usdt"] > 0).sum() if not df.empty else 0
    loss_count = (df["pnl_usdt"] <= 0).sum() if not df.empty else 0
    total_closed = len(df[df["status"] == "closed"]) if not df.empty else 0
    win_rate = win_count / max(total_closed, 1) * 100
    avg_win = df[df["pnl_usdt"] > 0]["pnl_usdt"].mean() if win_count > 0 else 0
    avg_loss = df[df["pnl_usdt"] <= 0]["pnl_usdt"].mean() if loss_count > 0 else 0
    profit_factor = abs(avg_win * win_count / (avg_loss * loss_count)) if avg_loss != 0 and loss_count > 0 else 0

    return {
        "total_pnl": round(total_pnl, 2),
        "win_count": int(win_count),
        "loss_count": int(loss_count),
        "total_closed": int(total_closed),
        "win_rate": round(win_rate, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
    }


@app.post("/api/command")
async def api_command(cmd: dict):
    """Receive commands from the frontend and queue them for the orchestrator."""
    cmd_path = settings.data_dir / "command_queue.json"
    try:
        queue = []
        if cmd_path.exists():
            with open(cmd_path) as f:
                queue = json.load(f)
        queue.append({
            "command": cmd.get("command"),
            "payload": cmd.get("payload", {}),
            "timestamp": datetime.utcnow().isoformat(),
        })
        with open(cmd_path, "w") as f:
            json.dump(queue, f)
        logger.info(f"[API] Command queued: {cmd.get('command')}")
        return {"status": "ok", "command": cmd.get("command")}
    except Exception as e:
        logger.error(f"[API] Command error: {e}")
        return {"status": "error", "detail": str(e)}


@app.get("/api/settings")
async def api_settings():
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
    }


# ── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial data burst
        trades = await load_trades(50)
        defense = await load_defense()
        agents = await load_agents()
        await manager.send_to(websocket, {
            "type": "init",
            "trades": trades,
            "defense": defense,
            "agents": agents,
        })

        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            if action == "ping":
                await manager.send_to(websocket, {"type": "pong"})
            elif action == "command":
                # Forward command through REST handler logic
                await api_command(msg.get("data", {}))
                await manager.send_to(websocket, {"type": "command_queued", "command": msg.get("data", {}).get("command")})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"[WS] Error: {e}")
        await manager.disconnect(websocket)


# ── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=3003, reload=False)
