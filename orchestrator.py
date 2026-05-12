"""
orchestrator.py
─────────────────────────────────────────────────────────────────────────────
Master Orchestrator — the "brain" of the Dual-Agent Composite Hedge System.

LangGraph-based stateful workflow:
  IDLE → SCANNING → CONSENSUS → ARMED → EXECUTING → MONITORING → CLOSING → IDLE

The orchestrator:
  1. Continuously scans the watchlist for high-opportunity setups
  2. Triggers the 100-agent swarm to evaluate each symbol
  3. Gates the trade through the Risk Manager
  4. Fires UpAgent + DownAgent concurrently (one atomic package)
  5. Monitors packages: rebalances, trailing stops, daily PnL
  6. Closes packages cleanly and stores memories

BUG FIXES (v2):
  • BUG 3 FIXED: node_execute() was double-opening legs.  The old code
    called up_agent.open_leg() (which already opens the leg AND attaches
    it to pkg.long_leg), then passed the result to
    open_both_legs_concurrently() which called open_long_leg() AGAIN.
    The fix: node_execute() now builds raw LegState objects and passes
    them directly to open_both_legs_concurrently(), then attaches the
    returned filled states to pkg.long_leg / pkg.short_leg.  The agent
    open_leg() methods are NOT called here — they are called by
    _attach_monitor() so agents can own their leg references for
    monitoring.  The execution path is now:
      build LegState → open_both_legs_concurrently() → attach to pkg
      → start monitor (agents reference pkg.long_leg/short_leg directly)

  • BUG 4 FIXED: SwarmSupervisor was instantiated with `SwarmSupervisor()`
    inside BOTH node_swarm_consensus() (a module-level node function) AND
    _monitor_all_packages() (called every 30s per active package).  Each
    instantiation calls build_swarm() which creates 100 new objects,
    causing a memory leak of 100 objects every signal_refresh_seconds per
    package.  Fix: a single SwarmSupervisor instance is created in
    Orchestrator.__init__() as self.supervisor and reused throughout the
    lifetime of the orchestrator.  The module-level node functions that
    need the supervisor now receive it via the state dict.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger

from config import settings
from down_agent import DownAgent
from exchange_client import (
    close_all_exchanges,
    fetch_market_snapshot,
    open_both_legs_concurrently,
)
from memory_store import memory_store
from models import (
    LegState,
    LegStatus,
    PackageStatus,
    Side,
    SwarmConsensus,
    TradePackage,
)
from risk_manager import compute_position_sizes, daily_tracker, qty_from_budget, risk_manager
from swarm_agents import SwarmSupervisor
from up_agent import UpAgent
from defense_swarm import (
    DefenseCoordinator,
    build_defense_coordinator,
    # BULL_RUN_THRESHOLD constant removed — the orchestrator now reads
    # settings.defense_bull_run_threshold directly (BUG 5 FIX).
)



# ─────────────────────────────────────────────────────────────────────────────
# LangGraph state schema
# ─────────────────────────────────────────────────────────────────────────────

class OrchestratorState(TypedDict):
    """Mutable state carried through the LangGraph workflow."""
    symbol: str
    consensus: Optional[SwarmConsensus]
    package: Optional[TradePackage]
    account_equity: float
    active_packages: Dict[str, TradePackage]   # package_id → TradePackage
    # BUG 4 FIX: supervisor is passed through state so node functions can
    # reuse the single Orchestrator-owned instance instead of creating new ones.
    supervisor: Optional[SwarmSupervisor]
    error: Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
# Node functions (each is one step in the graph)
# ─────────────────────────────────────────────────────────────────────────────

async def node_scan(state: OrchestratorState) -> OrchestratorState:
    """
    Quick pre-filter: check if the symbol is "interesting" before
    firing the full 100-agent swarm (saves LLM/API credits).
    """
    symbol = state["symbol"]
    try:
        snap = await fetch_market_snapshot(settings.long_exchange_id, symbol)
        # Rough pre-filter: skip if 24h volume is too low
        if snap.volume_24h < 1_000_000:
            logger.info(f"[Orchestrator] {symbol} skipped — low volume {snap.volume_24h:.0f}")
            state["error"] = "low_volume"
            return state
        logger.info(f"[Orchestrator] {symbol} passed pre-scan. Proceeding to swarm.")
        state["error"] = None
    except Exception as e:
        logger.error(f"[Orchestrator] node_scan error: {e}")
        state["error"] = str(e)
    return state


async def node_swarm_consensus(state: OrchestratorState) -> OrchestratorState:
    """
    Run the full 100-agent swarm and store the consensus.

    BUG 4 FIX: Uses state["supervisor"] (the Orchestrator singleton) instead
    of creating `SwarmSupervisor()` here, which would build 100 new objects
    on every evaluation.
    """
    if state.get("error"):
        return state

    # BUG 4 FIX: reuse the existing supervisor passed through state
    supervisor: Optional[SwarmSupervisor] = state.get("supervisor")
    if supervisor is None:
        # Fallback safety: if somehow supervisor wasn't injected, create one.
        # This should not happen in normal operation.
        logger.warning("[Orchestrator] supervisor not in state — creating fallback instance")
        supervisor = SwarmSupervisor()

    try:
        consensus = await supervisor.evaluate(state["symbol"])
        state["consensus"] = consensus
    except Exception as e:
        logger.error(f"[Orchestrator] swarm evaluation error: {e}")
        state["error"] = str(e)
    return state


async def node_risk_gate(state: OrchestratorState) -> OrchestratorState:
    """Gate the trade through the Risk Manager."""
    if state.get("error") or not state.get("consensus"):
        return state
    consensus = state["consensus"]
    active = state.get("active_packages", {})
    equity = state.get("account_equity", 10_000.0)

    approved = await risk_manager.approve_trade(
        consensus=consensus,
        account_equity=equity,
        existing_packages=len(active),
    )
    if not approved:
        state["error"] = "risk_rejected"
        logger.info(f"[Orchestrator] Trade rejected by risk manager for {state['symbol']}")
    return state


async def node_execute(state: OrchestratorState) -> OrchestratorState:
    """
    Build the TradePackage, size each leg, and fire both legs concurrently.

    BUG 3 FIX: The old code called up_agent.open_leg() (which opens the
    position AND attaches the LegState to pkg) THEN passed the result to
    open_both_legs_concurrently() which called open_long_leg() AGAIN —
    doubling the position size.

    Corrected execution flow:
      1. Build raw LegState objects with the correct sizes.
      2. Pass them directly to open_both_legs_concurrently() which fires
         open_long_leg() + open_short_leg() in parallel (one call each).
      3. Attach the returned filled LegState objects to pkg.long_leg /
         pkg.short_leg.
      4. UpAgent / DownAgent instances are stored on the Orchestrator for
         the monitoring phase; they read leg state from the pkg directly.
    """
    if state.get("error"):
        return state

    consensus: SwarmConsensus = state["consensus"]
    symbol = state["symbol"]
    equity = state.get("account_equity", 10_000.0)

    try:
        # ── Sizing ────────────────────────────────────────────────────────
        sizes = compute_position_sizes(equity, consensus, settings.default_leverage)
        snap = await fetch_market_snapshot(settings.long_exchange_id, symbol)
        mark_price = snap.mark_price

        long_qty = qty_from_budget(sizes["long_budget_usdt"], mark_price)
        short_qty = qty_from_budget(sizes["short_budget_usdt"], mark_price)

        if long_qty <= 0 or short_qty <= 0:
            state["error"] = "zero_quantity"
            return state

        # ── Create the package ────────────────────────────────────────────
        from config import settings as _cfg
        pkg = TradePackage(
            user_id=_cfg.default_trading_user,
            symbol=symbol,
            status=PackageStatus.ARMED,
            risk_budget_usdt=sizes["risk_budget_usdt"],
            consensus=consensus,
        )
        pkg.notes.append(f"Armed at {datetime.utcnow().isoformat()} | mark={mark_price}")

        # ── BUG 3 FIX: Build raw LegState objects — do NOT call ─────────
        # up_agent.open_leg() here.  That method opens the position AND
        # attaches the leg to pkg in one step; calling it then passing the
        # result to open_both_legs_concurrently() would execute two market
        # orders per leg.  Instead we build the LegState, open both via
        # open_both_legs_concurrently(), then attach to pkg manually.
        long_leg_raw = LegState(
            package_id=pkg.package_id,
            side=Side.LONG,
            exchange_id=settings.long_exchange_id,
            symbol=symbol,
            quantity=long_qty,
            leverage=settings.default_leverage,
            weight=consensus.long_weight,
        )
        short_leg_raw = LegState(
            package_id=pkg.package_id,
            side=Side.SHORT,
            exchange_id=settings.short_exchange_id,
            symbol=symbol,
            quantity=short_qty,
            leverage=settings.default_leverage,
            weight=consensus.short_weight,
        )

        # ── Fire both legs simultaneously (one market order each) ─────────
        long_leg, short_leg = await open_both_legs_concurrently(
            long_leg=long_leg_raw,
            short_leg=short_leg_raw,
            mark_price=mark_price,
        )

        # ── Attach filled legs to the package ─────────────────────────────
        pkg.long_leg = long_leg
        pkg.short_leg = short_leg
        pkg.status = PackageStatus.ACTIVE
        pkg.notes.append(
            f"Both legs open | long@{long_leg.entry_price} short@{short_leg.entry_price}"
        )

        state["package"] = pkg
        state["active_packages"][pkg.package_id] = pkg

        await memory_store.save_package(pkg, user_id=pkg.user_id)
        logger.info(f"[Orchestrator] Package {pkg.package_id} ACTIVE for {symbol}")

    except Exception as e:
        logger.error(f"[Orchestrator] node_execute error: {e}")
        state["error"] = str(e)

    return state


def route_after_gate(state: OrchestratorState) -> str:
    """Conditional edge: proceed to execute or abort."""
    if state.get("error"):
        return "abort"
    return "execute"


def route_after_scan(state: OrchestratorState) -> str:
    if state.get("error"):
        return "abort"
    return "swarm"


# ─────────────────────────────────────────────────────────────────────────────
# Build the LangGraph workflow
# ─────────────────────────────────────────────────────────────────────────────

# Module-level reference kept for backward compatibility (e.g. dashboard.py).
# Agents now receive defense via explicit instance attribute in _attach_monitor.
_global_defense: Optional[DefenseCoordinator] = None
_global_orchestrator: Optional["Orchestrator"] = None


def _get_global_defense() -> Optional[DefenseCoordinator]:
    """Return the global DefenseCoordinator singleton (set by Orchestrator.__init__)."""
    return _global_defense


def get_global_orchestrator() -> Optional["Orchestrator"]:
    """Return the global Orchestrator singleton (set by Orchestrator.__init__)."""
    return _global_orchestrator


def build_trade_graph() -> StateGraph:

    g = StateGraph(OrchestratorState)

    g.add_node("scan", node_scan)
    g.add_node("swarm", node_swarm_consensus)
    g.add_node("gate", node_risk_gate)
    g.add_node("execute", node_execute)
    g.add_node("abort", lambda s: s)   # no-op terminal node

    g.set_entry_point("scan")
    g.add_conditional_edges("scan", route_after_scan, {"abort": "abort", "swarm": "swarm"})
    g.add_edge("swarm", "gate")
    g.add_conditional_edges("gate", route_after_gate, {"abort": "abort", "execute": "execute"})
    g.add_edge("execute", END)
    g.add_edge("abort", END)

    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Main Orchestrator class
# ─────────────────────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Top-level controller. Runs the main event loop:
      • Scan each coin on the watchlist every signal_refresh_seconds
      • Manage active packages (monitor, rebalance, close)
      • Update daily equity / drawdown tracker

    BUG 4 FIX: self.supervisor is created ONCE in __init__ and reused
    for all swarm evaluations.  Previously, every scan cycle and every
    rebalance tick created a new SwarmSupervisor() (= 100 new objects
    every 30s per active package).
    """

    def __init__(self) -> None:
        global _global_orchestrator
        _global_orchestrator = self

        self.graph = build_trade_graph()
        self.active_packages: Dict[str, TradePackage] = {}
        self._up_agents: Dict[str, UpAgent] = {}
        self._down_agents: Dict[str, DownAgent] = {}
        self._stop_events: Dict[str, asyncio.Event] = {}
        self._monitor_tasks: Dict[str, asyncio.Task] = {}
        self._running = False
        self._last_scan_at: Optional[datetime] = None
        self._last_consensus: Optional[SwarmConsensus] = None
        # BUG 4 FIX: single supervisor instance — build_swarm() called once
        self.supervisor = SwarmSupervisor()
        logger.info("[Orchestrator] SwarmSupervisor instantiated (100 agents, singleton)")

        # Defense Swarm: 15-agent anti-bot layer, singleton, always constructed.
        # Activates only when bull_score >= settings.defense_bull_run_threshold.
        self.defense: DefenseCoordinator = build_defense_coordinator()
        # Wire escalation callback: if Defense fires a circuit break,
        # call self._on_defense_circuit_break(reason) to halt the affected package.
        self.defense.set_escalation_callback(self._on_defense_circuit_break)
        self._defense_bg_tasks: Dict[str, asyncio.Task] = {}   # package_id → OB task
        logger.info("[Orchestrator] DefenseCoordinator instantiated (15 defense agents)")
        # Expose singleton globally for dashboard / external readers
        global _global_defense
        _global_defense = self.defense

    # ─────────────────────────────────────────────────────────────────────
    # Startup / shutdown
    # ─────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await memory_store.initialize()
        await daily_tracker.set_start_equity(await self._fetch_equity())
        self._running = True
        logger.info("[Orchestrator] System started")
        await self._main_loop()

    async def stop(self) -> None:
        self._running = False
        # Cancel all monitor tasks
        for task in self._monitor_tasks.values():
            task.cancel()
        await asyncio.gather(*self._monitor_tasks.values(), return_exceptions=True)
        # Close all open packages
        for pkg in list(self.active_packages.values()):
            await self._close_package(pkg, reason="system_shutdown")
        await close_all_exchanges()
        await memory_store.close()
        logger.info("[Orchestrator] System stopped")

    # ─────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────

    async def _main_loop(self) -> None:
        while self._running:
            try:
                equity = await self._fetch_equity()
                await daily_tracker.update_equity(equity)

                if daily_tracker.is_halted:
                    logger.warning("[Orchestrator] Trading halted (daily circuit breaker). Sleeping 60s.")
                    await asyncio.sleep(60)
                    continue

                # Scan watchlist concurrently
                scan_tasks = [
                    self._scan_and_trade(symbol, equity)
                    for symbol in settings.watchlist
                    if symbol not in [p.symbol for p in self.active_packages.values()]
                ]
                if scan_tasks:
                    await asyncio.gather(*scan_tasks, return_exceptions=True)

                # Monitor active packages
                await self._monitor_all_packages()

                await asyncio.sleep(settings.signal_refresh_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Orchestrator] Main loop error: {e}")
                await asyncio.sleep(10)

    # ─────────────────────────────────────────────────────────────────────
    # Scan → Trade
    # ─────────────────────────────────────────────────────────────────────

    async def _scan_and_trade(self, symbol: str, equity: float) -> None:
        self._last_scan_at = datetime.utcnow()
        # BUG 4 FIX: pass self.supervisor through state so node_swarm_consensus
        # can reuse it instead of creating a new instance
        initial_state: OrchestratorState = {

            "symbol": symbol,
            "consensus": None,
            "package": None,
            "account_equity": equity,
            "active_packages": self.active_packages,
            "supervisor": self.supervisor,   # ← singleton passed through
            "error": None,
        }
        final_state = await self.graph.ainvoke(initial_state)

        consensus = final_state.get("consensus")
        if consensus:
            self._last_consensus = consensus

        pkg = final_state.get("package")
        if pkg and pkg.status == PackageStatus.ACTIVE:
            # ── Defense Swarm activation check ───────────────────────────
            # After the trade is open, check if the consensus bull_score
            # exceeds settings.defense_bull_run_threshold. If so, activate defense and start
            # the background order-book monitor for this package.
            if settings.defense_enabled and pkg.consensus:
                bs = pkg.consensus.bull_score
                # BUG 5 FIX: Use settings.defense_bull_run_threshold (user-configurable via
                # DEFENSE_BULL_RUN_THRESHOLD env var) instead of the hardcoded
                # BULL_RUN_THRESHOLD constant imported from defense_swarm.py (0.70).
                # Previously the config field was declared but never read — changing
                # DEFENSE_BULL_RUN_THRESHOLD in .env had zero effect.
                if bs >= settings.defense_bull_run_threshold and not self.defense.is_active:
                    await self.defense.activate(bs)
                    # Start background OB monitor for this symbol
                    bg_task = asyncio.create_task(
                        self.defense.run_background_monitor(
                            settings.long_exchange_id,
                            pkg.symbol,
                            settings.defense_ob_scan_interval_s,
                        ),
                        name=f"defense-bg-{pkg.package_id}",
                    )
                    self._defense_bg_tasks[pkg.package_id] = bg_task
                    logger.warning(
                        f"[Orchestrator] ⚔️  Defense Swarm active for {pkg.symbol} "
                        f"| bull_score={bs:.3f}"
                    )
            await self._attach_monitor(pkg)


    # ─────────────────────────────────────────────────────────────────────
    # Package monitoring
    # ─────────────────────────────────────────────────────────────────────

    async def _attach_monitor(self, pkg: TradePackage) -> None:
        """
        Attach concurrent monitor loops for both legs.

        BUG 3 FIX: UpAgent and DownAgent instances here are used ONLY for
        monitoring (monitor_loop, rebalance, close_leg).  They do NOT call
        open_leg() — the legs are already open and attached to pkg from
        node_execute().  The agents read pkg.long_leg / pkg.short_leg
        directly via the shared TradePackage reference.
        """
        stop_event = asyncio.Event()
        self._stop_events[pkg.package_id] = stop_event

        up = UpAgent()
        dn = DownAgent()
        up._defense = self.defense   # explicit reference (no global)
        dn._defense = self.defense
        self._up_agents[pkg.package_id] = up
        self._down_agents[pkg.package_id] = dn

        task = asyncio.create_task(
            self._dual_monitor(pkg, up, dn, stop_event),
            name=f"monitor-{pkg.package_id}",
        )
        self._monitor_tasks[pkg.package_id] = task

    async def _dual_monitor(
        self,
        pkg: TradePackage,
        up: UpAgent,
        dn: DownAgent,
        stop_event: asyncio.Event,
    ) -> None:
        """
        Run both agent monitor loops concurrently.
        Either loop can set stop_event to trigger a package close.
        """
        await asyncio.gather(
            up.monitor_loop(pkg, stop_event),
            dn.monitor_loop(pkg, stop_event),
            return_exceptions=True,
        )
        # After either loop exits, close the whole package
        reason = "monitor_exit"
        kill, kill_reason = risk_manager.should_kill_package(pkg)
        if kill:
            reason = kill_reason
        await self._close_package(pkg, reason=reason)

    async def _monitor_all_packages(self) -> None:
        """Package-level checks on every tick (rebalance, kill-switch)."""
        for pid, pkg in list(self.active_packages.items()):
            if pkg.status != PackageStatus.ACTIVE:
                continue
            try:
                # Update PnL from current prices
                pkg.update_combined_pnl()

                # Kill check
                kill, reason = risk_manager.should_kill_package(pkg)
                if kill:
                    logger.warning(f"[Orchestrator] Killing package {pid}: {reason}")
                    stop = self._stop_events.get(pid)
                    if stop:
                        stop.set()
                    continue

                # Rebalance check — BUG 4 FIX: reuse self.supervisor
                new_consensus = await self.supervisor.evaluate(pkg.symbol)
                rebal = risk_manager.compute_rebalance(pkg, new_consensus)

                if rebal:
                    snap = await fetch_market_snapshot(settings.long_exchange_id, pkg.symbol)
                    up = self._up_agents.get(pid)
                    dn = self._down_agents.get(pid)
                    if up:
                        await up.rebalance(pkg, rebal.new_long_weight, snap.mark_price)
                    if dn:
                        await dn.rebalance(pkg, rebal.new_short_weight, snap.mark_price)
                    pkg.notes.append(f"Rebalanced: {rebal.rationale}")
                    await memory_store.save_package(pkg, user_id=pkg.user_id)

            except Exception as e:
                logger.error(f"[Orchestrator] Monitor error for {pid}: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # Package close
    # ─────────────────────────────────────────────────────────────────────

    async def _close_package(self, pkg: TradePackage, reason: str = "") -> None:
        if pkg.status in (PackageStatus.CLOSED, PackageStatus.KILLED):
            return

        pkg.status = PackageStatus.CLOSING
        logger.info(f"[Orchestrator] Closing package {pkg.package_id}. Reason: {reason}")

        up = self._up_agents.get(pkg.package_id, UpAgent())
        dn = self._down_agents.get(pkg.package_id, DownAgent())

        await asyncio.gather(
            up.close_leg(pkg, reason),
            dn.close_leg(pkg, reason),
            return_exceptions=True,
        )

        pkg.status = PackageStatus.CLOSED
        pkg.close_reason = reason
        pkg.closed_at = datetime.utcnow()
        pkg.update_combined_pnl()
        pkg.notes.append(f"Closed: {reason} | final_pnl={pkg.combined_pnl:.4f}")

        await memory_store.save_package(pkg, user_id=pkg.user_id)
        await memory_store.store_trade_memory(pkg)

        self.active_packages.pop(pkg.package_id, None)
        # Stop the defense background OB monitor for this package
        self._stop_defense_for_package(pkg.package_id)
        # If no more active packages, deactivate the defense swarm
        if not self.active_packages and self.defense.is_active:
            await self.defense.deactivate()
            logger.info("[Orchestrator] All packages closed — Defense Swarm deactivated")
        logger.info(
            f"[Orchestrator] Package {pkg.package_id} CLOSED. "
            f"PnL={pkg.combined_pnl:.2f} USDT | reason={reason}"
        )


    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────
    # Defense Swarm escalation callback
    # ─────────────────────────────────────────────────────────────────────

    async def _on_defense_circuit_break(self, reason: str) -> None:
        """
        Called by DefenseCoordinator when cumulative interference severity
        exceeds the circuit-break threshold.

        Actions:
          1. Log at CRITICAL level (visible in dashboard + log file)
          2. Close ALL active packages immediately
          3. Deactivate the Defense Swarm (resets rotators + circuit breakers)
          4. The daily circuit breaker is NOT necessarily triggered — the system
             will resume scanning on the next cycle once defense is cleared.
        """
        logger.critical(
            f"[Orchestrator] 🛑 DEFENSE CIRCUIT BREAK: {reason}. "
            f"Closing all {len(self.active_packages)} active packages."
        )
        for pkg in list(self.active_packages.values()):
            logger.warning(
                f"[Orchestrator] Emergency close package {pkg.package_id} "
                f"due to defense circuit break"
            )
            stop = self._stop_events.get(pkg.package_id)
            if stop:
                stop.set()
            await self._close_package(pkg, reason=f"defense_circuit_break:{reason}")

        # Cancel background OB monitor tasks
        for pid, task in list(self._defense_bg_tasks.items()):
            task.cancel()
        self._defense_bg_tasks.clear()

        # Deactivate Defense Swarm so it can re-engage cleanly next cycle
        await self.defense.deactivate()
        logger.info("[Orchestrator] Defense Swarm deactivated after circuit break. Will re-scan next cycle.")

    def _stop_defense_for_package(self, package_id: str) -> None:
        """Cancel the background OB task for a specific package on close."""
        task = self._defense_bg_tasks.pop(package_id, None)
        if task and not task.done():
            task.cancel()
            logger.debug(f"[Orchestrator] Defense BG monitor cancelled for {package_id}")

    async def _fetch_equity(self) -> float:

        """
        Fetch account balance from the primary exchange.
        Falls back to a fixed mock in paper-trading mode.
        """
        if settings.paper_trading:
            return 10_000.0
        try:
            from exchange_client import get_exchange
            ex = await get_exchange(settings.long_exchange_id)
            balance = await ex.fetch_balance()
            return float(balance["USDT"]["free"] or balance["USDT"]["total"] or 10_000)
        except Exception as e:
            logger.warning(f"[Orchestrator] Could not fetch equity: {e} — using 10000")
            return 10_000.0
