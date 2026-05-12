"""
defense_swarm.py
─────────────────────────────────────────────────────────────────────────────
Anti-Bot Defense Swarm — 15 specialist micro-agents that activate during
detected bull-run conditions and protect every order placement from:
  • API rate-limiting / throttling
  • Order rejections and unusual slippage
  • Liquidity sweeps and fake order-book walls
  • Front-running and manipulative order-book patterns
  • Exchange-side anti-bot flags, IP blocks, account restrictions

Architecture:
  ┌─ DefenseCoordinator ────────────────────────────────────────────────────┐
  │  Activated by Orchestrator when bull_score > BULL_RUN_THRESHOLD        │
  │  Wraps every place_market_order() call via defended_place_order()      │
  └──────────────────────────┬──────────────────────────────────────────────┘
                             │
   ┌─────────┬──────────┬────┴──────┬──────────┬──────────┬───────────────┐
   │Detector │ Rotator  │ Stealth   │ Retry    │ OrderBook│ CircuitBreaker│
   │(3)      │ (2)      │ Executor  │ Strategist│ Monitor  │ Alert (2)     │
   │         │          │ (3)       │ (2)       │ (2)      │               │
   └─────────┴──────────┴───────────┴──────────┴──────────┴───────────────┘

Every order placed when the defense swarm is active goes through:
  1. OrderBook sanity check (fake-wall detection)
  2. Stealth sizing/timing randomisation
  3. Primary exchange attempt with backoff
  4. Automatic rotation to backup exchange if primary fails
  5. Interference event logged to vector DB for Reflection agents

Integration:
  • Import DefenseCoordinator and call .start(consensus) in Orchestrator
  • Replace direct exchange_client calls with coordinator.defended_place_order()
  • Dashboard reads coordinator.get_defense_status() for live panel
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

from loguru import logger

from config import settings
from exchange_client import (
    fetch_market_snapshot,
    fetch_order_book,
    get_exchange,
    place_market_order,
)
from models import Side


# ─────────────────────────────────────────────────────────────────────────────
# Defense-specific enums and data models
# ─────────────────────────────────────────────────────────────────────────────

class InterferenceType(str, Enum):
    """Categories of interference the Defense Swarm can detect."""
    RATE_LIMIT        = "rate_limit"         # HTTP 429 / exchange throttle
    ORDER_REJECTION   = "order_rejection"    # Exchange refused the order
    UNUSUAL_SLIPPAGE  = "unusual_slippage"   # Fill price >> expected price
    FAKE_WALL         = "fake_wall"          # Large order disappeared on fill
    FRONT_RUN         = "front_run"          # Rapid cancel/replace pattern
    IP_BLOCK          = "ip_block"           # Connection error / 403
    LATENCY_SPIKE     = "latency_spike"      # Round-trip time > threshold
    ACCOUNT_FLAG      = "account_flag"       # Exchange returned auth error
    LIQUIDITY_SWEEP   = "liquidity_sweep"    # OB imbalance > sweep threshold


class DefenseAction(str, Enum):
    """Actions the Defense Swarm can take autonomously."""
    BACKOFF_RETRY       = "backoff_retry"
    ROTATE_EXCHANGE     = "rotate_exchange"
    STEALTH_SPLIT       = "stealth_split"        # split order into micro-lots
    RANDOMISE_TIMING    = "randomise_timing"
    PAUSE_RESUBMIT      = "pause_resubmit"
    ALERT_SUPERVISOR    = "alert_supervisor"
    CIRCUIT_BREAK       = "circuit_break"


@dataclass
class InterferenceEvent:
    """One recorded interference incident."""
    event_id:      str               = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp:     datetime          = field(default_factory=datetime.utcnow)
    exchange_id:   str               = ""
    symbol:        str               = ""
    itype:         InterferenceType  = InterferenceType.RATE_LIMIT
    severity:      float             = 0.5          # 0-1
    detail:        str               = ""
    action_taken:  DefenseAction     = DefenseAction.BACKOFF_RETRY
    resolved:      bool              = False


@dataclass
class DefenseStatus:
    """
    Snapshot of Defense Swarm state — read by the dashboard.
    """
    active:               bool                      = False
    bull_run_detected:    bool                      = False
    bull_score:           float                     = 0.0
    active_exchange:      str                       = ""
    backup_exchange:      str                       = ""
    total_events:         int                       = 0
    unresolved_events:    int                       = 0
    last_action:          Optional[DefenseAction]   = None
    last_event_detail:    str                       = ""
    circuit_broken:       bool                      = False
    rotations_today:      int                       = 0
    stealth_splits_today: int                       = 0
    updated_at:           datetime                  = field(default_factory=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration constants (tunable via environment in a future iteration)
# ─────────────────────────────────────────────────────────────────────────────

BULL_RUN_THRESHOLD: float = 0.70       # bull_score above this → activate defense
RATE_LIMIT_HTTP_CODES = {429, 418}     # HTTP codes that indicate throttling
MAX_RETRY_ATTEMPTS: int = 5            # max retries per order
BASE_BACKOFF_SECONDS: float = 0.5      # base for exponential backoff
MAX_BACKOFF_SECONDS: float = 30.0      # ceiling on backoff delay
SLIPPAGE_WARN_PCT: float = 0.3         # warn if fill > 0.3% from expected
SLIPPAGE_SEVERE_PCT: float = 1.0       # severe if fill > 1.0% from expected
OB_FAKE_WALL_RATIO: float = 5.0        # wall is "fake" if > 5x avg book depth
LATENCY_WARN_MS: float = 800.0         # warn if exchange RTT > 800ms
OB_SWEEP_IMBALANCE: float = 0.80       # bid/ask imbalance > 80% = possible sweep
MAX_STEALTH_SPLITS: int = 5            # max sub-orders when splitting
MIN_STEALTH_DELAY_S: float = 0.1       # minimum random delay between splits
MAX_STEALTH_DELAY_S: float = 2.0       # maximum random delay between splits



# ─────────────────────────────────────────────────────────────────────────────
# ① InterferenceDetector (3 instances)
# ─────────────────────────────────────────────────────────────────────────────

class InterferenceDetector:
    """
    Analyses raw exchange errors and order outcomes to classify interference.
    Three instances run concurrently — one for each active exchange endpoint.
    """

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id = agent_id or f"det-{uuid.uuid4().hex[:4]}"
        # Rolling window of recent RTT samples (ms)
        self._rtt_window: Deque[float] = deque(maxlen=20)

    def record_rtt(self, rtt_ms: float) -> None:
        """Update rolling RTT average with a new measurement."""
        self._rtt_window.append(rtt_ms)

    @property
    def avg_rtt_ms(self) -> float:
        return sum(self._rtt_window) / len(self._rtt_window) if self._rtt_window else 0.0

    def classify_exception(
        self,
        exc: Exception,
        exchange_id: str,
        symbol: str,
    ) -> Optional[InterferenceEvent]:
        """
        Inspect a CCXT / network exception and return a typed InterferenceEvent,
        or None if the error is not deemed interference (e.g., a normal timeout).
        """
        msg = str(exc).lower()

        # Rate-limiting
        if any(code in msg for code in ("429", "418", "too many requests", "rate limit")):
            return InterferenceEvent(
                exchange_id=exchange_id, symbol=symbol,
                itype=InterferenceType.RATE_LIMIT, severity=0.6,
                detail=f"Rate-limit signal: {exc}",
                action_taken=DefenseAction.BACKOFF_RETRY,
            )

        # IP / auth block
        if any(t in msg for t in ("403", "ip ban", "blocked", "unauthorized", "invalid api")):
            return InterferenceEvent(
                exchange_id=exchange_id, symbol=symbol,
                itype=InterferenceType.IP_BLOCK, severity=0.9,
                detail=f"IP/auth block: {exc}",
                action_taken=DefenseAction.ROTATE_EXCHANGE,
            )

        # Account flag / margin errors
        if any(t in msg for t in ("account", "margin", "insufficient", "suspend")):
            return InterferenceEvent(
                exchange_id=exchange_id, symbol=symbol,
                itype=InterferenceType.ACCOUNT_FLAG, severity=0.8,
                detail=f"Account flag: {exc}",
                action_taken=DefenseAction.ALERT_SUPERVISOR,
            )

        # Order rejection
        if any(t in msg for t in ("reject", "cancel", "invalid order", "post only")):
            return InterferenceEvent(
                exchange_id=exchange_id, symbol=symbol,
                itype=InterferenceType.ORDER_REJECTION, severity=0.5,
                detail=f"Order rejected: {exc}",
                action_taken=DefenseAction.STEALTH_SPLIT,
            )

        return None  # Not classified as interference

    def classify_slippage(
        self,
        expected_price: float,
        fill_price: float,
        exchange_id: str,
        symbol: str,
    ) -> Optional[InterferenceEvent]:
        """Classify fill price deviation as potential interference."""
        if expected_price <= 0:
            return None
        slip_pct = abs(fill_price - expected_price) / expected_price * 100
        if slip_pct >= SLIPPAGE_SEVERE_PCT:
            return InterferenceEvent(
                exchange_id=exchange_id, symbol=symbol,
                itype=InterferenceType.UNUSUAL_SLIPPAGE, severity=min(slip_pct / 2, 1.0),
                detail=f"Severe slippage: expected={expected_price:.2f} fill={fill_price:.2f} ({slip_pct:.2f}%)",
                action_taken=DefenseAction.STEALTH_SPLIT,
            )
        if slip_pct >= SLIPPAGE_WARN_PCT:
            logger.warning(
                f"[Defense:{self.agent_id}] Slippage warning {slip_pct:.2f}% on {symbol}@{exchange_id}"
            )
        return None

    def classify_latency(self, rtt_ms: float, exchange_id: str, symbol: str) -> Optional[InterferenceEvent]:
        """Flag latency spike — may indicate network-level interference."""
        if rtt_ms > LATENCY_WARN_MS:
            return InterferenceEvent(
                exchange_id=exchange_id, symbol=symbol,
                itype=InterferenceType.LATENCY_SPIKE, severity=min(rtt_ms / 3000, 1.0),
                detail=f"Latency spike: {rtt_ms:.0f}ms > {LATENCY_WARN_MS:.0f}ms threshold",
                action_taken=DefenseAction.BACKOFF_RETRY,
            )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ② OrderBookMonitor (2 instances)
# ─────────────────────────────────────────────────────────────────────────────

class OrderBookMonitor:
    """
    Scans the order book for fake walls, liquidity sweeps, and front-running
    patterns (rapid large-order cancellations near the spread).
    """

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id = agent_id or f"obm-{uuid.uuid4().hex[:4]}"
        # Store recent book snapshots for delta comparison
        self._prev_bids: List[List] = []
        self._prev_asks: List[List] = []

    async def scan(
        self, exchange_id: str, symbol: str
    ) -> Optional[InterferenceEvent]:
        """
        Fetch the order book and check for:
          1. Fake walls (huge single order dwarfing avg depth)
          2. Liquidity sweeps (bid/ask imbalance > threshold)
          3. Front-running (large orders appearing then vanishing near spread)
        """
        try:
            ob = await fetch_order_book(exchange_id, symbol, depth=20)
        except Exception as e:
            logger.debug(f"[OBMonitor:{self.agent_id}] fetch_order_book error: {e}")
            return None

        bids = ob.get("bids", [])
        asks = ob.get("asks", [])

        if not bids or not asks:
            return None

        # ── Fake-wall detection ───────────────────────────────────────────
        bid_sizes = [b[1] for b in bids[:10]]
        ask_sizes = [a[1] for a in asks[:10]]

        if bid_sizes:
            avg_bid = sum(bid_sizes) / len(bid_sizes)
            max_bid = max(bid_sizes)
            if max_bid > avg_bid * OB_FAKE_WALL_RATIO:
                evt = InterferenceEvent(
                    exchange_id=exchange_id, symbol=symbol,
                    itype=InterferenceType.FAKE_WALL, severity=0.65,
                    detail=f"Fake bid wall detected: max={max_bid:.2f} avg={avg_bid:.2f}",
                    action_taken=DefenseAction.STEALTH_SPLIT,
                )
                logger.warning(f"[OBMonitor:{self.agent_id}] {evt.detail}")
                self._prev_bids = bids
                self._prev_asks = asks
                return evt

        # ── Liquidity sweep detection ──────────────────────────────────────
        total_bid_vol = sum(b[1] for b in bids[:10])
        total_ask_vol = sum(a[1] for a in asks[:10])
        total_vol = total_bid_vol + total_ask_vol
        if total_vol > 0:
            bid_ratio = total_bid_vol / total_vol
            if bid_ratio > OB_SWEEP_IMBALANCE or bid_ratio < (1 - OB_SWEEP_IMBALANCE):
                evt = InterferenceEvent(
                    exchange_id=exchange_id, symbol=symbol,
                    itype=InterferenceType.LIQUIDITY_SWEEP, severity=0.55,
                    detail=f"Liquidity imbalance: bid_ratio={bid_ratio:.2f}",
                    action_taken=DefenseAction.RANDOMISE_TIMING,
                )
                logger.info(f"[OBMonitor:{self.agent_id}] {evt.detail}")
                self._prev_bids = bids
                self._prev_asks = asks
                return evt

        # ── Front-run detection (large orders that vanished since last scan) ─
        if self._prev_bids:
            prev_bid_prices = {round(b[0], 1) for b in self._prev_bids[:5]}
            curr_bid_prices = {round(b[0], 1) for b in bids[:5]}
            vanished = prev_bid_prices - curr_bid_prices
            if len(vanished) >= 3:
                evt = InterferenceEvent(
                    exchange_id=exchange_id, symbol=symbol,
                    itype=InterferenceType.FRONT_RUN, severity=0.70,
                    detail=f"Front-run pattern: {len(vanished)} large bids vanished",
                    action_taken=DefenseAction.RANDOMISE_TIMING,
                )
                logger.warning(f"[OBMonitor:{self.agent_id}] {evt.detail}")
                self._prev_bids = bids
                self._prev_asks = asks
                return evt

        self._prev_bids = bids
        self._prev_asks = asks
        return None


# ─────────────────────────────────────────────────────────────────────────────
# ③ RetryStrategist (2 instances)
# ─────────────────────────────────────────────────────────────────────────────

class RetryStrategist:
    """
    Implements exponential backoff with full jitter for retrying failed orders.
    Tracks per-exchange failure counts to trigger rotation.
    """

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id = agent_id or f"ret-{uuid.uuid4().hex[:4]}"
        self._failure_counts: Dict[str, int] = {}  # exchange_id → fail count

    def record_failure(self, exchange_id: str) -> None:
        self._failure_counts[exchange_id] = self._failure_counts.get(exchange_id, 0) + 1

    def record_success(self, exchange_id: str) -> None:
        """Reset failure count on success — exchange is healthy again."""
        self._failure_counts[exchange_id] = 0

    def get_failure_count(self, exchange_id: str) -> int:
        return self._failure_counts.get(exchange_id, 0)

    def should_rotate(self, exchange_id: str, threshold: int = 3) -> bool:
        """Return True if this exchange has failed too many times in a row."""
        return self.get_failure_count(exchange_id) >= threshold

    def compute_delay(self, attempt: int) -> float:
        """
        Full-jitter exponential backoff.
        delay = random(0, min(MAX_BACKOFF, BASE * 2^attempt))
        This avoids thundering-herd if multiple agents retry simultaneously.
        """
        cap = min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * (2 ** attempt))
        return random.uniform(0, cap)


# ─────────────────────────────────────────────────────────────────────────────
# ④ StealthExecutor (3 instances)
# ─────────────────────────────────────────────────────────────────────────────

class StealthExecutor:
    """
    Randomises order size and timing to prevent pattern detection.
    Splits large orders into micro-lots with random delays.
    """

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id = agent_id or f"stl-{uuid.uuid4().hex[:4]}"

    def randomise_quantity(self, quantity: float) -> float:
        """
        Add ±2% random noise to the order size.
        Small enough not to affect risk, large enough to break patterns.
        """
        noise = random.uniform(-0.02, 0.02)
        return round(quantity * (1 + noise), 8)

    def split_order(self, quantity: float) -> List[float]:
        """
        Split quantity into 2–MAX_STEALTH_SPLITS random-sized lots.
        Each lot is randomised so the split pattern itself isn't predictable.
        """
        n_splits = random.randint(2, MAX_STEALTH_SPLITS)
        # Generate random weights that sum to 1
        weights = [random.random() for _ in range(n_splits)]
        total_w = sum(weights)
        sizes = [round(quantity * w / total_w, 8) for w in weights]
        # Adjust last lot to absorb rounding error
        sizes[-1] = round(quantity - sum(sizes[:-1]), 8)
        return [s for s in sizes if s > 0]

    async def place_stealth_order(
        self,
        exchange_id: str,
        symbol: str,
        side: Side,
        quantity: float,
        reduce_only: bool = False,
    ) -> List[Dict]:
        """
        Place a stealth order: split into micro-lots with randomised delays.
        Returns list of order results (one per lot).
        """
        lots = self.split_order(quantity)
        results: List[Dict] = []
        logger.info(
            f"[Stealth:{self.agent_id}] Splitting {quantity} {symbol} into "
            f"{len(lots)} stealth lots: {[round(l, 6) for l in lots]}"
        )
        for i, lot_qty in enumerate(lots):
            # Random delay between lots to break temporal patterns
            delay = random.uniform(MIN_STEALTH_DELAY_S, MAX_STEALTH_DELAY_S)
            if i > 0:  # no delay before the first lot
                logger.debug(
                    f"[Stealth:{self.agent_id}] Waiting {delay:.2f}s before lot {i+1}/{len(lots)}"
                )
                await asyncio.sleep(delay)
            try:
                result = await place_market_order(
                    exchange_id=exchange_id,
                    symbol=symbol,
                    side=side,
                    quantity=lot_qty,
                    reduce_only=reduce_only,
                )
                results.append(result)
                logger.info(
                    f"[Stealth:{self.agent_id}] Lot {i+1}/{len(lots)} placed: "
                    f"qty={lot_qty} id={result.get('id', 'N/A')}"
                )
            except Exception as e:
                logger.error(f"[Stealth:{self.agent_id}] Lot {i+1} failed: {e}")
                # Continue remaining lots even if one fails
        return results


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ ExchangeRotator (2 instances)
# ─────────────────────────────────────────────────────────────────────────────

class ExchangeRotator:
    """
    Maintains an ordered list of available exchanges and rotates the active
    exchange when the primary is experiencing interference.
    """

    def __init__(
        self,
        primary: str,
        backups: List[str],
        agent_id: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id or f"rot-{uuid.uuid4().hex[:4]}"
        self._priority: List[str] = [primary] + backups   # ordered by preference
        self._current_idx: int = 0
        self._lock = asyncio.Lock()

    @property
    def current_exchange(self) -> str:
        return self._priority[self._current_idx]

    async def rotate(self, reason: str = "") -> str:
        """
        Advance to the next exchange in priority order.
        Wraps around — if all exchanges fail, returns to primary.
        Returns the new active exchange ID.
        """
        async with self._lock:
            prev = self.current_exchange
            self._current_idx = (self._current_idx + 1) % len(self._priority)
            new = self.current_exchange
            logger.warning(
                f"[Rotator:{self.agent_id}] Exchange rotation: "
                f"{prev} → {new} | reason: {reason}"
            )
            return new

    async def reset(self) -> None:
        """Return to primary exchange."""
        async with self._lock:
            self._current_idx = 0
            logger.info(f"[Rotator:{self.agent_id}] Reset to primary: {self.current_exchange}")


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ CircuitBreakerAlert (2 instances)
# ─────────────────────────────────────────────────────────────────────────────

class CircuitBreakerAlert:
    """
    Tracks cumulative interference severity and fires a package-level
    circuit breaker when repeated severe interference is detected.
    """

    def __init__(
        self,
        max_severity_sum: float = 3.0,
        window_seconds: float = 120.0,
        agent_id: Optional[str] = None,
    ) -> None:
        self.agent_id = agent_id or f"cba-{uuid.uuid4().hex[:4]}"
        self._max_severity = max_severity_sum   # total severity before circuit break
        self._window = window_seconds
        self._events: Deque[Tuple[float, float]] = deque()  # (timestamp, severity)
        self._lock = asyncio.Lock()

    async def record(self, severity: float) -> bool:
        """
        Record an interference severity score.
        Returns True if the circuit breaker should now fire.
        """
        async with self._lock:
            now = time.time()
            self._events.append((now, severity))
            # Prune events outside the rolling window
            while self._events and now - self._events[0][0] > self._window:
                self._events.popleft()

            total = sum(s for _, s in self._events)
            if total >= self._max_severity:
                logger.critical(
                    f"[CircuitBreaker:{self.agent_id}] CIRCUIT BREAK TRIGGERED: "
                    f"cumulative severity={total:.2f} in {self._window:.0f}s window"
                )
                return True
        return False

    async def reset(self) -> None:
        async with self._lock:
            self._events.clear()



# ─────────────────────────────────────────────────────────────────────────────
# DefenseCoordinator — top-level class that the Orchestrator talks to
# ─────────────────────────────────────────────────────────────────────────────

class DefenseCoordinator:
    """
    Central controller for the 15-agent Defense Swarm.

    Activation:
      • Called by Orchestrator.__init__() as a singleton.
      • .activate(consensus) is called when bull_score > BULL_RUN_THRESHOLD.
      • .deactivate() is called when bull conditions subside or package closes.

    Order pipeline (when active):
      Every order flows through .defended_place_order() which:
        1. Runs OrderBookMonitor scan (detect fake walls / sweeps)
        2. Optionally randomises quantity via StealthExecutor
        3. Attempts order with exponential backoff via RetryStrategist
        4. Rotates exchange via ExchangeRotator if retries exhausted
        5. Logs all events to self._events (read by dashboard)
        6. Checks CircuitBreakerAlert — escalates to Supervisor if triggered

    Non-interference path:
      When defense is NOT active, .defended_place_order() calls
      place_market_order() directly with zero overhead.
    """

    def __init__(
        self,
        primary_long_exchange: str,
        primary_short_exchange: str,
        backup_exchanges: Optional[List[str]] = None,
    ) -> None:
        # ── Agent pool setup ──────────────────────────────────────────────
        self.detectors  = [InterferenceDetector() for _ in range(3)]
        self.ob_monitors = [OrderBookMonitor() for _ in range(2)]
        self.retry_agents = [RetryStrategist() for _ in range(2)]
        self.stealth_execs = [StealthExecutor() for _ in range(3)]

        backups = backup_exchanges or []
        # Rotator for the LONG leg exchange
        long_backups = [e for e in backups if e != primary_long_exchange]
        if primary_short_exchange not in long_backups:
            long_backups.append(primary_short_exchange)   # cross-side backup

        # Rotator for the SHORT leg exchange
        short_backups = [e for e in backups if e != primary_short_exchange]
        if primary_long_exchange not in short_backups:
            short_backups.append(primary_long_exchange)

        self.long_rotator  = ExchangeRotator(primary_long_exchange, long_backups)
        self.short_rotator = ExchangeRotator(primary_short_exchange, short_backups)
        # BUG 7 FIX: Pass settings.defense_circuit_severity_threshold to each
        # CircuitBreakerAlert instead of using the hardcoded default (3.0).
        # Previously the config field defense_circuit_severity_threshold was
        # declared in config.py / .env but never actually read — changing the
        # env var had zero effect.  Now it correctly wires to both breakers.
        self.circuit_breakers = [
            CircuitBreakerAlert(max_severity_sum=settings.defense_circuit_severity_threshold)
            for _ in range(2)
        ]

        # ── State ──────────────────────────────────────────────────────────
        self._bull_run_threshold = settings.defense_bull_run_threshold
        self._active = False
        self._circuit_broken = False
        self._bull_score: float = 0.0
        self._events: Deque[InterferenceEvent] = deque(maxlen=500)
        self._rotations_today: int = 0
        self._stealth_splits_today: int = 0
        self._lock = asyncio.Lock()

        # Reference to Orchestrator's escalation callback (injected after init)
        self._escalation_cb = None

        logger.info(
            f"[DefenseCoordinator] Initialized | long={primary_long_exchange} "
            f"short={primary_short_exchange} backups={backups}"
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def set_escalation_callback(self, cb) -> None:
        """
        Inject a callback that the Coordinator calls when a circuit break
        fires. The Orchestrator registers self._on_defense_circuit_break here.
        """
        self._escalation_cb = cb

    async def activate(self, bull_score: float) -> None:
        """Activate the Defense Swarm — called by Orchestrator on bull run."""
        if bull_score < self._bull_run_threshold:
            return
        async with self._lock:
            self._active = True
            self._bull_score = bull_score
        logger.warning(
            f"[DefenseCoordinator] ⚔️  DEFENSE SWARM ACTIVATED | "
            f"bull_score={bull_score:.3f} >= threshold={self._bull_run_threshold}"
        )

    async def deactivate(self) -> None:
        """Deactivate and reset all state — called when bull run subsides."""
        async with self._lock:
            self._active = False
            self._circuit_broken = False
            self._bull_score = 0.0
        await self.long_rotator.reset()
        await self.short_rotator.reset()
        for cb in self.circuit_breakers:
            await cb.reset()
        logger.info("[DefenseCoordinator] Defense swarm deactivated — all rotators reset")

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_circuit_broken(self) -> bool:
        return self._circuit_broken

    # ── Main defended order pipeline ───────────────────────────────────────

    async def defended_place_order(
        self,
        exchange_id: str,
        symbol: str,
        side: Side,
        quantity: float,
        reduce_only: bool = False,
        use_stealth: bool = False,
        expected_price: float = 0.0,
    ) -> Dict:
        """
        DEFENSE-WRAPPED order placement.

        When defense is inactive: zero overhead, direct call.
        When defense is active:
          1. Pre-flight OB scan
          2. Optional stealth splitting
          3. Retry loop with backoff + exchange rotation

        Returns the final order result dict (same schema as place_market_order).
        Raises RuntimeError if circuit breaker fires — caller must escalate.
        """
        if not self._active:
            # Fast path — defense not engaged
            return await place_market_order(exchange_id, symbol, side, quantity, reduce_only)

        if self._circuit_broken:
            raise RuntimeError(
                f"[DefenseCoordinator] Circuit breaker is active — "
                f"order {side.value} {quantity} {symbol} blocked"
            )

        # ── Step 1: Pre-flight order-book scan ────────────────────────────
        ob_event = await self.ob_monitors[0].scan(exchange_id, symbol)
        if ob_event:
            await self._record_event(ob_event)
            await self._check_circuit_break(ob_event.severity)

        # ── Step 2: Choose stealth vs single order ─────────────────────────
        active_rotator = (
            self.long_rotator if side == Side.LONG else self.short_rotator
        )
        retry_agent = self.retry_agents[0]
        detector = self.detectors[0]

        if use_stealth or (ob_event and ob_event.itype in (
            InterferenceType.FAKE_WALL, InterferenceType.LIQUIDITY_SWEEP
        )):
            # Stealth-split the order
            self._stealth_splits_today += 1
            stealth = self.stealth_execs[0]
            randomised_qty = stealth.randomise_quantity(quantity)
            logger.info(
                f"[DefenseCoordinator] Using stealth split: {quantity} → {randomised_qty} "
                f"({self._stealth_splits_today} splits today)"
            )
            try:
                results = await stealth.place_stealth_order(
                    active_rotator.current_exchange, symbol, side, randomised_qty, reduce_only
                )
                if results:
                    retry_agent.record_success(active_rotator.current_exchange)
                    # Return a merged synthetic result for the caller
                    return self._merge_lot_results(results, symbol)
            except Exception as e:
                await self._handle_exception(e, active_rotator.current_exchange, symbol, detector, retry_agent)

        # ── Step 3: Standard order with backoff retry loop ─────────────────
        last_exception: Optional[Exception] = None
        for attempt in range(MAX_RETRY_ATTEMPTS):
            current_ex = active_rotator.current_exchange
            t0 = time.monotonic()
            try:
                result = await place_market_order(
                    current_ex, symbol, side, quantity, reduce_only
                )
                rtt_ms = (time.monotonic() - t0) * 1000
                detector.record_rtt(rtt_ms)

                # Check for latency spike
                lat_event = detector.classify_latency(rtt_ms, current_ex, symbol)
                if lat_event:
                    await self._record_event(lat_event)

                # Check slippage if expected price provided
                fill_price = result.get("average") or 0.0
                if fill_price and expected_price:
                    slip_event = detector.classify_slippage(
                        expected_price, fill_price, current_ex, symbol
                    )
                    if slip_event:
                        await self._record_event(slip_event)

                retry_agent.record_success(current_ex)
                if attempt > 0:
                    logger.info(
                        f"[DefenseCoordinator] Order succeeded on attempt {attempt+1} "
                        f"via {current_ex}"
                    )
                return result

            except Exception as exc:
                last_exception = exc
                rtt_ms = (time.monotonic() - t0) * 1000
                detector.record_rtt(rtt_ms)

                event = await self._handle_exception(
                    exc, current_ex, symbol, detector, retry_agent
                )
                if event:
                    await self._check_circuit_break(event.severity)

                # Rotate exchange if retry agent says so
                if retry_agent.should_rotate(current_ex):
                    new_ex = await active_rotator.rotate(reason=str(exc)[:80])
                    self._rotations_today += 1
                    retry_agent.record_success(new_ex)  # reset count for new exchange
                    logger.warning(
                        f"[DefenseCoordinator] Rotated to {new_ex} "
                        f"({self._rotations_today} rotations today)"
                    )
                else:
                    delay = retry_agent.compute_delay(attempt)
                    logger.info(
                        f"[DefenseCoordinator] Backoff {delay:.2f}s "
                        f"(attempt {attempt+1}/{MAX_RETRY_ATTEMPTS})"
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        err_msg = (
            f"[DefenseCoordinator] All {MAX_RETRY_ATTEMPTS} attempts exhausted "
            f"for {side.value} {quantity} {symbol}. Last error: {last_exception}"
        )
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _handle_exception(
        self,
        exc: Exception,
        exchange_id: str,
        symbol: str,
        detector: InterferenceDetector,
        retry_agent: RetryStrategist,
    ) -> Optional[InterferenceEvent]:
        """Classify exception, record failure, log event."""
        retry_agent.record_failure(exchange_id)
        event = detector.classify_exception(exc, exchange_id, symbol)
        if event:
            await self._record_event(event)
            logger.warning(
                f"[DefenseCoordinator] Interference detected: "
                f"[{event.itype.value}] {event.detail} → action={event.action_taken.value}"
            )
        else:
            logger.error(f"[DefenseCoordinator] Unclassified error on {exchange_id}: {exc}")
        return event

    async def _record_event(self, event: InterferenceEvent) -> None:
        """Thread-safe event recording + memory-store logging."""
        self._events.append(event)
        # Also persist to vector DB via memory_store for Reflection agents
        try:
            from memory_store import memory_store
            if getattr(memory_store, '_collection', None) is not None:
                doc = (
                    f"Defense interference: type={event.itype.value} "
                    f"exchange={event.exchange_id} symbol={event.symbol} "
                    f"severity={event.severity:.2f} detail={event.detail} "
                    f"action={event.action_taken.value}"
                )
                memory_store._collection.add(
                    documents=[doc],
                    ids=[f"def-{event.event_id}"],
                    metadatas=[{
                        "type": "defense_event",
                        "itype": event.itype.value,
                        "exchange": event.exchange_id,
                        "symbol": event.symbol,
                        "severity": event.severity,
                        "timestamp": event.timestamp.isoformat(),
                    }],
                )
        except Exception as e:
            logger.debug(f"[DefenseCoordinator] Could not persist event to vector DB: {e}")

    async def _check_circuit_break(self, severity: float) -> None:
        """Check all circuit breakers and escalate if any fires."""
        for cb in self.circuit_breakers:
            tripped = await cb.record(severity)
            if tripped and not self._circuit_broken:
                self._circuit_broken = True
                if self._escalation_cb:
                    asyncio.create_task(
                        self._escalation_cb("defense_circuit_break")
                    )
                break

    @staticmethod
    def _merge_lot_results(results: List[Dict], symbol: str) -> Dict:
        """Merge multiple lot fills into one logical result for the caller."""
        total_filled = sum(r.get("filled", 0) for r in results)
        avg_prices = [r.get("average", 0) for r in results if r.get("average", 0)]
        avg_price = sum(avg_prices) / len(avg_prices) if avg_prices else 0.0
        return {
            "id": f"STEALTH-MERGED-{uuid.uuid4().hex[:6]}",
            "status": "closed",
            "average": avg_price,
            "filled": total_filled,
            "symbol": symbol,
            "lots": len(results),
        }

    # ── Background OB monitoring task ──────────────────────────────────────

    async def run_background_monitor(
        self,
        exchange_id: str,
        symbol: str,
        interval_seconds: float = 5.0,
    ) -> None:
        """
        Continuously scan the order book every `interval_seconds` while
        the defense swarm is active. Call as asyncio.create_task().
        """
        logger.info(
            f"[DefenseCoordinator] Background OB monitor started: "
            f"{symbol} @ {exchange_id} every {interval_seconds}s"
        )
        monitor = self.ob_monitors[1]   # use second monitor for background task
        while self._active:
            try:
                event = await monitor.scan(exchange_id, symbol)
                if event:
                    await self._record_event(event)
                    await self._check_circuit_break(event.severity)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[DefenseCoordinator] BG monitor error: {e}")
            await asyncio.sleep(interval_seconds)

    # ── Status for dashboard ───────────────────────────────────────────────

    def get_defense_status(self) -> DefenseStatus:
        """
        Return a snapshot of current defense state.
        Called by dashboard.py on every refresh cycle.
        """
        unresolved = sum(1 for e in self._events if not e.resolved)
        last_event = self._events[-1] if self._events else None
        return DefenseStatus(
            active=self._active,
            bull_run_detected=self._active,
            bull_score=self._bull_score,
            active_exchange=self.long_rotator.current_exchange,
            backup_exchange=self.long_rotator._priority[1] if len(self.long_rotator._priority) > 1 else "",
            total_events=len(self._events),
            unresolved_events=unresolved,
            last_action=last_event.action_taken if last_event else None,
            last_event_detail=last_event.detail if last_event else "",
            circuit_broken=self._circuit_broken,
            rotations_today=self._rotations_today,
            stealth_splits_today=self._stealth_splits_today,
            updated_at=datetime.utcnow(),
        )

    def get_recent_events(self, n: int = 50) -> List[InterferenceEvent]:
        """Return the N most recent interference events (newest first)."""
        events = list(self._events)
        return list(reversed(events[-n:]))


# ─────────────────────────────────────────────────────────────────────────────
# Singleton factory — called once by the Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def build_defense_coordinator() -> DefenseCoordinator:
    """
    Construct a DefenseCoordinator from settings.
    Backup exchanges = all configured exchanges that differ from the primaries.
    """
    all_exchanges = []
    for ex in ["bybit", "okx", "binance"]:
        kw = settings.get_exchange_kwargs(ex)
        # Only include exchanges that have API keys configured
        if kw.get("apiKey"):
            all_exchanges.append(ex)

    backups = [
        e for e in all_exchanges
        if e not in (settings.long_exchange_id, settings.short_exchange_id)
    ]

    coordinator = DefenseCoordinator(
        primary_long_exchange=settings.long_exchange_id,
        primary_short_exchange=settings.short_exchange_id,
        backup_exchanges=backups,
    )
    logger.info(
        f"[DefenseCoordinator] Built with {3+2+2+3+2+2} agents | "
        f"primary_long={settings.long_exchange_id} "
        f"primary_short={settings.short_exchange_id} "
        f"backups={backups}"
    )
    return coordinator
