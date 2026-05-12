"""
models.py
─────────────────────────────────────────────────────────────────────────────
Shared Pydantic data-models used across every module.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class LegStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    KILLED = "killed"


class PackageStatus(str, Enum):
    WAITING = "waiting"       # swarm analyzing
    ARMED = "armed"           # swarm approved, ready to fire
    ACTIVE = "active"         # both legs open
    REBALANCING = "rebalancing"
    CLOSING = "closing"
    CLOSED = "closed"
    KILLED = "killed"         # circuit-breaker triggered


class SignalStrength(str, Enum):
    STRONG_BULL = "strong_bull"
    MILD_BULL = "mild_bull"
    NEUTRAL = "neutral"
    MILD_BEAR = "mild_bear"
    STRONG_BEAR = "strong_bear"


class AgentRole(str, Enum):
    SUPERVISOR = "supervisor"
    UP_AGENT = "up_agent"
    DOWN_AGENT = "down_agent"
    SENTIMENT = "sentiment"
    TECHNICAL = "technical"
    ONCHAIN = "onchain"
    VOLATILITY = "volatility"
    RISK = "risk"
    EXECUTION = "execution"
    REFLECTION = "reflection"
    MACRO = "macro"
    FUNDING = "funding"
    ORDERFLOW = "orderflow"
    NEWS = "news"
    # Defense Swarm roles (added for anti-bot defense layer)
    DEFENSE_DETECTOR   = "defense_detector"
    DEFENSE_ROTATOR    = "defense_rotator"
    DEFENSE_STEALTH    = "defense_stealth"
    DEFENSE_RETRY      = "defense_retry"
    DEFENSE_OB_MONITOR = "defense_ob_monitor"
    DEFENSE_CIRCUIT    = "defense_circuit"


# ─────────────────────────────────────────────────────────────────────────────
# Signal / Vote models
# ─────────────────────────────────────────────────────────────────────────────

class AgentVote(BaseModel):
    agent_id: str
    role: AgentRole
    signal: SignalStrength
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SwarmConsensus(BaseModel):
    """Aggregated vote from the 100-agent swarm."""
    symbol: str
    bull_score: float = Field(..., ge=0.0, le=1.0)   # weighted bullish vote
    bear_score: float = Field(..., ge=0.0, le=1.0)   # weighted bearish vote
    volatility_percentile: float = 0.0               # 0–100
    expected_move_pct: float = 0.0                   # e.g. 3.5 = ±3.5% expected
    consensus_score: float = Field(..., ge=0.0, le=1.0)
    trigger_trade: bool = False
    long_weight: float = 0.5                         # recommended leg split
    short_weight: float = 0.5
    votes: List[AgentVote] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Leg / Package models
# ─────────────────────────────────────────────────────────────────────────────

class LegState(BaseModel):
    """State of one directional leg (long or short)."""
    leg_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    package_id: str
    side: Side
    exchange_id: str
    symbol: str
    entry_price: float = 0.0
    current_price: float = 0.0
    quantity: float = 0.0                # in base currency
    leverage: int = 5
    notional_usdt: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    funding_paid: float = 0.0
    stop_loss_price: float = 0.0
    take_profit_price: float = 0.0
    trailing_stop_price: Optional[float] = None
    status: LegStatus = LegStatus.PENDING
    order_id: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    weight: float = 0.5                  # 0–1; fraction of package risk budget

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.side == Side.LONG:
            return (self.current_price - self.entry_price) / self.entry_price * 100 * self.leverage
        else:
            return (self.entry_price - self.current_price) / self.entry_price * 100 * self.leverage

    @property
    def is_active(self) -> bool:
        return self.status == LegStatus.OPEN


class TradePackage(BaseModel):
    """
    Atomic composite trade: one long leg + one short leg
    bound by a shared risk budget.
    """
    package_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "system"                      # tenant isolation — iron clad RLS
    symbol: str                                  # e.g. "BTC/USDT:USDT"
    status: PackageStatus = PackageStatus.WAITING
    long_leg: Optional[LegState] = None
    short_leg: Optional[LegState] = None
    risk_budget_usdt: float = 0.0               # total capital at risk
    peak_combined_pnl: float = 0.0
    combined_pnl: float = 0.0
    consensus: Optional[SwarmConsensus] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    close_reason: str = ""
    notes: List[str] = Field(default_factory=list)

    def update_combined_pnl(self) -> None:
        pnl = 0.0
        if self.long_leg:
            pnl += self.long_leg.unrealized_pnl + self.long_leg.realized_pnl
        if self.short_leg:
            pnl += self.short_leg.unrealized_pnl + self.short_leg.realized_pnl
        self.combined_pnl = pnl
        if pnl > self.peak_combined_pnl:
            self.peak_combined_pnl = pnl
        self.updated_at = datetime.utcnow()


# ─────────────────────────────────────────────────────────────────────────────
# Market data models
# ─────────────────────────────────────────────────────────────────────────────

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class FundingRate(BaseModel):
    symbol: str
    exchange_id: str
    rate: float          # e.g. 0.0001 = 0.01%
    next_funding_time: Optional[datetime] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MarketSnapshot(BaseModel):
    """All real-time market data for one symbol."""
    symbol: str
    bid: float
    ask: float
    last: float
    mark_price: float
    index_price: float
    open_interest: float    # in USDT
    funding_rate: float
    volume_24h: float
    change_24h_pct: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Memory record
# ─────────────────────────────────────────────────────────────────────────────

class TradeMemory(BaseModel):
    """Stored in vector DB for reflection / learning."""
    package_id: str
    symbol: str
    entry_consensus: Dict
    outcome_pnl_pct: float
    close_reason: str
    lessons_learned: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Rebalance instruction
# ─────────────────────────────────────────────────────────────────────────────

class RebalanceInstruction(BaseModel):
    package_id: str
    new_long_weight: float
    new_short_weight: float
    rationale: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
