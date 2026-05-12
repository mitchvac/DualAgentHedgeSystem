from __future__ import annotations

"""
swarm_agents.py
Agent role counts can be overridden via set_agent_role_config().
"""

# ── Agent role configuration (overridable at runtime) ──────────────────────

_DEFAULT_AGENT_COUNTS = {
    "SENTIMENT": 15,
    "TWITTER_SENTIMENT": 5,
    "TECHNICAL": 20,
    "VOLATILITY": 10,
    "ONCHAIN": 15,
    "FUNDING": 10,
    "ORDERFLOW": 15,
    "MACRO": 5,
    "NEWS": 5,
    "REFLECTION": 5,
}

_AGENT_ROLE_CONFIG: dict = {}


def set_agent_role_config(cfg: dict) -> None:
    """Update agent role counts from external config (e.g. SQLite)."""
    global _AGENT_ROLE_CONFIG
    _AGENT_ROLE_CONFIG = {k: int(v) for k, v in cfg.items() if v is not None}


def _get_count(role: str, default: int) -> int:
    """Get agent count for a role, respecting runtime overrides."""
    return _AGENT_ROLE_CONFIG.get(role, default)


# ── Imports ─────────────────────────────────────────────────────────────────

import asyncio
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from loguru import logger

from config import settings
from exchange_client import fetch_market_snapshot, fetch_ohlcv, fetch_funding_rate
from models import (
    AgentRole,
    AgentVote,
    SignalStrength,
    SwarmConsensus,
)


# ─────────────────────────────────────────────────────────────────────────────
# Base specialist agent
# ─────────────────────────────────────────────────────────────────────────────

class BaseSpecialistAgent(ABC):
    """Abstract base for all swarm specialist agents."""

    # Subclasses set their own weight (influence on final consensus)
    VOTE_WEIGHT: float = 1.0
    ROLE: AgentRole = AgentRole.SENTIMENT

    def __init__(self, agent_id: Optional[str] = None) -> None:
        self.agent_id = agent_id or f"{self.ROLE.value[:4]}-{uuid.uuid4().hex[:4]}"

    @abstractmethod
    async def analyze(self, symbol: str) -> AgentVote:
        """Run analysis and return a vote."""
        ...

    def _make_vote(
        self,
        signal: SignalStrength,
        confidence: float,
        rationale: str,
    ) -> AgentVote:
        return AgentVote(
            agent_id=self.agent_id,
            role=self.ROLE,
            signal=signal,
            confidence=min(max(confidence, 0.0), 1.0),
            rationale=rationale,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ① Sentiment Team (15 agents)
# ─────────────────────────────────────────────────────────────────────────────

class SentimentAgent(BaseSpecialistAgent):
    """
    Reads social sentiment from LunarCrush API (or Twitter bearer token).
    Each agent queries a slightly different window or source.
    """
    VOTE_WEIGHT = 0.8
    ROLE = AgentRole.SENTIMENT

    def __init__(self, source: str = "lunarcrush", **kwargs) -> None:
        super().__init__(**kwargs)
        self.source = source

    async def analyze(self, symbol: str) -> AgentVote:
        coin = symbol.split("/")[0].upper()   # BTC, ETH, SOL …
        try:
            score = await self._fetch_sentiment(coin)
            if score > 0.65:
                return self._make_vote(SignalStrength.STRONG_BULL, score, f"Positive social sentiment score={score:.2f}")
            elif score > 0.52:
                return self._make_vote(SignalStrength.MILD_BULL, score, f"Mild positive sentiment score={score:.2f}")
            elif score < 0.35:
                return self._make_vote(SignalStrength.STRONG_BEAR, 1 - score, f"Negative social sentiment score={score:.2f}")
            elif score < 0.48:
                return self._make_vote(SignalStrength.MILD_BEAR, 1 - score, f"Mild negative sentiment score={score:.2f}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "Neutral sentiment")
        except Exception as e:
            logger.debug(f"[SentimentAgent] {e}")
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, f"Data unavailable: {e}")

    async def _fetch_sentiment(self, coin: str) -> float:
        """
        Returns sentiment score 0.0 (bearish) – 1.0 (bullish).
        Returns 0.5 (neutral) with zero confidence if API key is missing.
        """
        if not settings.lunarcrush_api_key:
            logger.warning("[SentimentAgent] LUNARCRUSH_API_KEY not set — returning neutral sentiment")
            return 0.5

        url = f"https://lunarcrush.com/api4/public/coins/{coin}/v1"
        headers = {"Authorization": f"Bearer {settings.lunarcrush_api_key}"}
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json().get("data", {})
            # galaxy_score: 0–100; normalize to 0–1
            galaxy = data.get("galaxy_score", 50) / 100.0
            alt_rank = data.get("alt_rank", 500)
            # alt_rank 1 = most bullish; invert and normalize
            rank_score = max(0, 1 - alt_rank / 1000)
            return (galaxy + rank_score) / 2.0


class TwitterSentimentAgent(BaseSpecialistAgent):
    """Queries recent tweet volume + weighted positive/negative ratio."""
    VOTE_WEIGHT = 0.6
    ROLE = AgentRole.SENTIMENT

    async def analyze(self, symbol: str) -> AgentVote:
        coin = symbol.split("/")[0].upper()
        try:
            score = await self._twitter_score(coin)
            if score > 0.6:
                return self._make_vote(SignalStrength.MILD_BULL, score, f"Twitter bullish score={score:.2f}")
            elif score < 0.4:
                return self._make_vote(SignalStrength.MILD_BEAR, 1 - score, f"Twitter bearish score={score:.2f}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "Twitter neutral")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, f"Twitter unavailable: {e}")

    async def _twitter_score(self, coin: str) -> float:
        if not settings.twitter_bearer_token:
            logger.warning("[TwitterSentimentAgent] TWITTER_BEARER_TOKEN not set — returning neutral sentiment")
            return 0.5
        # Simplified: count recent mentions with positive/negative keywords
        # Production: integrate tweepy search_recent_tweets
        logger.warning("[TwitterSentimentAgent] Real Twitter integration not yet implemented — returning neutral sentiment")
        return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# ② Technical Analysis Team (20 agents)
# ─────────────────────────────────────────────────────────────────────────────

class TechnicalAgent(BaseSpecialistAgent):
    """
    Multiple instances each analyse a different timeframe or indicator.
    """
    VOTE_WEIGHT = 1.2
    ROLE = AgentRole.TECHNICAL

    def __init__(self, timeframe: str = "1h", indicator: str = "composite", **kwargs) -> None:
        super().__init__(**kwargs)
        self.timeframe = timeframe
        self.indicator = indicator

    async def analyze(self, symbol: str) -> AgentVote:
        import numpy as np, pandas as pd
        try:
            bars = await fetch_ohlcv(settings.long_exchange_id, symbol, self.timeframe, 200)
            closes = [b[4] for b in bars]
            highs  = [b[2] for b in bars]
            lows   = [b[3] for b in bars]
            volumes= [b[5] for b in bars]
            score, note = self._score(closes, highs, lows, volumes)
            signal = self._score_to_signal(score)
            return self._make_vote(signal, abs(score - 0.5) * 2, f"{self.indicator}@{self.timeframe}: {note}")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, str(e))

    def _score(self, closes, highs, lows, volumes) -> Tuple[float, str]:
        """Return (0-1 score, note). 0.5=neutral, >0.5=bullish, <0.5=bearish."""
        import numpy as np, pandas as pd
        c = pd.Series(closes)
        score = 0.5
        notes = []

        if self.indicator in ("composite", "ema"):
            ema20 = c.ewm(span=20).mean().iloc[-1]
            ema50 = c.ewm(span=50).mean().iloc[-1]
            if ema20 > ema50: score += 0.10; notes.append("EMA20>50↑")
            else: score -= 0.10; notes.append("EMA20<50↓")

        if self.indicator in ("composite", "rsi"):
            delta = c.diff(); g = delta.clip(lower=0); l = -delta.clip(upper=0)
            rs = g.rolling(14).mean() / l.rolling(14).mean()
            rsi = (100 - 100/(1+rs)).iloc[-1]
            if rsi < 35: score += 0.15; notes.append(f"RSI_oversold={rsi:.0f}")
            elif rsi > 70: score -= 0.15; notes.append(f"RSI_overbought={rsi:.0f}")

        if self.indicator in ("composite", "bbands"):
            mid = c.rolling(20).mean()
            std = c.rolling(20).std()
            upper = mid + 2 * std; lower = mid - 2 * std
            if c.iloc[-1] < lower.iloc[-1]: score += 0.10; notes.append("price@LowerBand")
            elif c.iloc[-1] > upper.iloc[-1]: score -= 0.10; notes.append("price@UpperBand")

        if self.indicator in ("composite", "macd"):
            fast = c.ewm(span=12).mean(); slow = c.ewm(span=26).mean()
            hist = (fast - slow - (fast - slow).ewm(span=9).mean()).iloc[-1]
            if hist > 0: score += 0.10; notes.append("MACD_hist+")
            else: score -= 0.10; notes.append("MACD_hist-")

        return min(max(score, 0.0), 1.0), " | ".join(notes)

    def _score_to_signal(self, score: float) -> SignalStrength:
        if score >= 0.75: return SignalStrength.STRONG_BULL
        if score >= 0.58: return SignalStrength.MILD_BULL
        if score <= 0.25: return SignalStrength.STRONG_BEAR
        if score <= 0.42: return SignalStrength.MILD_BEAR
        return SignalStrength.NEUTRAL


# ─────────────────────────────────────────────────────────────────────────────
# ③ Volatility Team (10 agents)
# ─────────────────────────────────────────────────────────────────────────────

class VolatilityAgent(BaseSpecialistAgent):
    """
    Estimates realised volatility and historical percentile.
    High vol → trade is worth opening (regardless of direction).
    """
    VOTE_WEIGHT = 1.0
    ROLE = AgentRole.VOLATILITY

    async def analyze(self, symbol: str) -> AgentVote:
        import numpy as np
        try:
            bars = await fetch_ohlcv(settings.long_exchange_id, symbol, "1h", 200)
            closes = [b[4] for b in bars]
            returns = np.diff(np.log(closes))
            rv = np.std(returns[-24:]) * np.sqrt(24 * 365) * 100  # annualised RV %
            pct = self._percentile(returns)
            note = f"RV={rv:.1f}% ann, {pct:.0f}th percentile"
            # Volatility doesn't give direction but confirms trade worthiness
            if pct > 70:
                return self._make_vote(SignalStrength.NEUTRAL, pct / 100, f"HIGH_VOL {note}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, pct / 100, f"LOW_VOL {note}")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.5, str(e))

    def _percentile(self, returns) -> float:
        import numpy as np
        if len(returns) < 50:
            return 50.0
        recent_rv = np.std(returns[-24:])
        all_rvs = [np.std(returns[i:i+24]) for i in range(0, len(returns)-24, 24)]
        return float(np.searchsorted(sorted(all_rvs), recent_rv) / len(all_rvs) * 100)


# ─────────────────────────────────────────────────────────────────────────────
# ④ On-Chain Team (15 agents)
# ─────────────────────────────────────────────────────────────────────────────

class OnChainAgent(BaseSpecialistAgent):
    """
    Queries Glassnode / on-chain metrics: exchange netflow, whale activity,
    SOPR, MVRV, active addresses.
    Returns neutral signal with warning when API key is absent.
    """
    VOTE_WEIGHT = 1.1
    ROLE = AgentRole.ONCHAIN

    def __init__(self, metric: str = "exchange_netflow", **kwargs) -> None:
        super().__init__(**kwargs)
        self.metric = metric

    async def analyze(self, symbol: str) -> AgentVote:
        coin = symbol.split("/")[0].lower()
        try:
            score, note = await self._fetch_metric(coin)
            signal = self._score_to_signal(score)
            return self._make_vote(signal, abs(score - 0.5) * 2, f"{self.metric}: {note}")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, str(e))

    async def _fetch_metric(self, coin: str) -> Tuple[float, str]:
        if not settings.glassnode_api_key:
            logger.warning("[OnChainAgent] GLASSNODE_API_KEY not set — returning neutral on-chain signal")
            return 0.5, "no_api_key"
        # Production: call Glassnode API
        # GET https://api.glassnode.com/v1/metrics/transactions/transfers_volume_sum
        # Headers: {"X-Api-Key": settings.glassnode_api_key}
        url = f"https://api.glassnode.com/v1/metrics/indicators/sopr"
        headers = {"X-Api-Key": settings.glassnode_api_key}
        params = {"a": coin.upper(), "i": "24h"}
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            sopr = data[-1]["v"] if data else 1.0
            # SOPR > 1 = profitable sells → mild bearish; < 1 = capitulation → bullish
            score = 0.5 + (1.0 - sopr) * 0.3
            return min(max(score, 0), 1), f"SOPR={sopr:.3f}"

    def _score_to_signal(self, score: float) -> SignalStrength:
        if score >= 0.70: return SignalStrength.STRONG_BULL
        if score >= 0.55: return SignalStrength.MILD_BULL
        if score <= 0.30: return SignalStrength.STRONG_BEAR
        if score <= 0.45: return SignalStrength.MILD_BEAR
        return SignalStrength.NEUTRAL


# ─────────────────────────────────────────────────────────────────────────────
# ⑤ Funding Rate Team (10 agents)
# ─────────────────────────────────────────────────────────────────────────────

class FundingRateAgent(BaseSpecialistAgent):
    """
    Analyses funding rates across multiple exchanges to detect lopsided positioning.
    """
    VOTE_WEIGHT = 1.0
    ROLE = AgentRole.FUNDING

    async def analyze(self, symbol: str) -> AgentVote:
        try:
            fr = await fetch_funding_rate(settings.long_exchange_id, symbol)
            rate = fr.rate
            # Positive funding = longs pay shorts → over-extended long crowd → bearish signal
            # Negative funding = shorts pay longs → squeezed shorts → bullish signal
            if rate < -0.0002:
                return self._make_vote(SignalStrength.STRONG_BULL, 0.8, f"Extreme negative funding={rate:.5f}")
            elif rate < -0.0001:
                return self._make_vote(SignalStrength.MILD_BULL, 0.6, f"Negative funding={rate:.5f}")
            elif rate > 0.0003:
                return self._make_vote(SignalStrength.STRONG_BEAR, 0.8, f"Extreme positive funding={rate:.5f}")
            elif rate > 0.0001:
                return self._make_vote(SignalStrength.MILD_BEAR, 0.6, f"Positive funding={rate:.5f}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, f"Neutral funding={rate:.5f}")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ⑥ Order-Flow Team (15 agents)
# ─────────────────────────────────────────────────────────────────────────────

class OrderFlowAgent(BaseSpecialistAgent):
    """
    Analyses order book imbalance and large print detection
    (whale alerts, liquidation heatmap).
    """
    VOTE_WEIGHT = 0.9
    ROLE = AgentRole.ORDERFLOW

    async def analyze(self, symbol: str) -> AgentVote:
        from exchange_client import fetch_order_book
        try:
            ob = await fetch_order_book(settings.long_exchange_id, symbol, depth=20)
            bid_vol = sum(b[1] for b in ob["bids"][:10])
            ask_vol = sum(a[1] for a in ob["asks"][:10])
            total = bid_vol + ask_vol
            if total == 0:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "Empty order book")
            imbalance = (bid_vol - ask_vol) / total   # +1=all bids, -1=all asks
            confidence = abs(imbalance)
            if imbalance > 0.15:
                return self._make_vote(SignalStrength.MILD_BULL, confidence, f"Order book bid imbalance={imbalance:.2f}")
            elif imbalance < -0.15:
                return self._make_vote(SignalStrength.MILD_BEAR, confidence, f"Order book ask imbalance={imbalance:.2f}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, f"Balanced order book imbalance={imbalance:.2f}")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ⑦ Macro Team (5 agents)
# ─────────────────────────────────────────────────────────────────────────────

class MacroAgent(BaseSpecialistAgent):
    """
    Monitors macro events: DXY correlation, BTC dominance, fear & greed index,
    FOMC calendar. Lightweight rule-based scoring.
    """
    VOTE_WEIGHT = 0.7
    ROLE = AgentRole.MACRO

    async def analyze(self, symbol: str) -> AgentVote:
        try:
            score = await self._fear_greed_score()
            if score > 0.70:
                return self._make_vote(SignalStrength.STRONG_BULL, score, f"Macro greed={score:.2f}")
            elif score > 0.55:
                return self._make_vote(SignalStrength.MILD_BULL, score, f"Macro mild greed={score:.2f}")
            elif score < 0.30:
                return self._make_vote(SignalStrength.STRONG_BEAR, 1 - score, f"Macro fear={score:.2f}")
            elif score < 0.45:
                return self._make_vote(SignalStrength.MILD_BEAR, 1 - score, f"Macro mild fear={score:.2f}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "Macro neutral")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.4, str(e))

    async def _fear_greed_score(self) -> float:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("https://api.alternative.me/fng/?limit=1")
                data = r.json()["data"][0]
                return int(data["value"]) / 100.0
        except Exception as e:
            logger.warning(f"[MacroAgent] Fear & Greed API failed: {e} — returning neutral macro signal")
            return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# ⑧ News Team (5 agents)
# ─────────────────────────────────────────────────────────────────────────────

class NewsAgent(BaseSpecialistAgent):
    """
    Parses crypto news headlines for sentiment.
    Uses CryptoPanic free API (no key needed).
    """
    VOTE_WEIGHT = 0.6
    ROLE = AgentRole.NEWS

    async def analyze(self, symbol: str) -> AgentVote:
        coin = symbol.split("/")[0].upper()
        try:
            bullish, bearish = await self._headline_score(coin)
            total = bullish + bearish
            if total == 0:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "No recent news")
            ratio = bullish / total
            if ratio > 0.65:
                return self._make_vote(SignalStrength.MILD_BULL, ratio, f"News: {bullish}B/{bearish}Be")
            elif ratio < 0.35:
                return self._make_vote(SignalStrength.MILD_BEAR, 1 - ratio, f"News: {bullish}B/{bearish}Be")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "Mixed news")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.3, str(e))

    async def _headline_score(self, coin: str) -> Tuple[int, int]:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token=&currencies={coin}&public=true"
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return 0, 0
            posts = r.json().get("results", [])[:20]
            bullish = sum(1 for p in posts if p.get("kind") == "positive")
            bearish = sum(1 for p in posts if p.get("kind") == "negative")
            return bullish, bearish


# ─────────────────────────────────────────────────────────────────────────────
# ⑨ Reflection Team (5 agents)
# ─────────────────────────────────────────────────────────────────────────────

class ReflectionAgent(BaseSpecialistAgent):
    """
    Queries the vector DB of past trades to find similar market conditions
    and what outcome they produced (regime-aware historical learning).
    """
    VOTE_WEIGHT = 0.9
    ROLE = AgentRole.REFLECTION

    async def analyze(self, symbol: str) -> AgentVote:
        try:
            from memory_store import memory_store
            score = await memory_store.query_similar_outcome(symbol)
            if score > 0.6:
                return self._make_vote(SignalStrength.MILD_BULL, score, f"Historical recall bullish={score:.2f}")
            elif score < 0.4:
                return self._make_vote(SignalStrength.MILD_BEAR, 1 - score, f"Historical recall bearish={score:.2f}")
            else:
                return self._make_vote(SignalStrength.NEUTRAL, 0.5, "No strong historical signal")
        except Exception as e:
            return self._make_vote(SignalStrength.NEUTRAL, 0.4, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Swarm Factory — builds the full 100-agent roster
# ─────────────────────────────────────────────────────────────────────────────

def build_swarm() -> List[BaseSpecialistAgent]:
    """
    Instantiate ~100 specialist agents.
    Adjust counts here to scale up/down.
    """
    agents: List[BaseSpecialistAgent] = []

    # Sentiment: configurable split between LunarCrush + Twitter
    sentiment_total = _get_count("SENTIMENT", 15)
    twitter_count = _get_count("TWITTER_SENTIMENT", 5)
    lunar_count = max(0, sentiment_total - twitter_count)
    for _ in range(lunar_count):
        agents.append(SentimentAgent(source="lunarcrush"))
    for _ in range(twitter_count):
        agents.append(TwitterSentimentAgent())

    # Technical: configurable (default 20 = 4 timeframes × 5 indicators)
    tech_total = _get_count("TECHNICAL", 20)
    timeframes = ("5m", "15m", "1h", "4h")
    indicators = ("composite", "rsi", "ema", "macd", "bbands")
    # Build all combos, take first N
    tech_combos = [(tf, ind) for tf in timeframes for ind in indicators]
    for i in range(min(tech_total, len(tech_combos))):
        agents.append(TechnicalAgent(timeframe=tech_combos[i][0], indicator=tech_combos[i][1]))

    # Volatility
    for _ in range(_get_count("VOLATILITY", 10)):
        agents.append(VolatilityAgent())

    # On-Chain: configurable (default 15 = 5 metrics × 3)
    onchain_total = _get_count("ONCHAIN", 15)
    metrics = ("exchange_netflow", "sopr", "whale_alert", "mvrv", "active_addresses")
    per_metric = max(1, onchain_total // len(metrics))
    for metric in metrics:
        for _ in range(per_metric):
            agents.append(OnChainAgent(metric=metric))

    # Funding rate
    for _ in range(_get_count("FUNDING", 10)):
        agents.append(FundingRateAgent())

    # Order flow
    for _ in range(_get_count("ORDERFLOW", 15)):
        agents.append(OrderFlowAgent())

    # Macro
    for _ in range(_get_count("MACRO", 5)):
        agents.append(MacroAgent())

    # News
    for _ in range(_get_count("NEWS", 5)):
        agents.append(NewsAgent())

    # Reflection
    for _ in range(_get_count("REFLECTION", 5)):
        agents.append(ReflectionAgent())

    logger.info(f"[Swarm] Built {len(agents)} specialist agents (config: {_AGENT_ROLE_CONFIG})")
    return agents


# ─────────────────────────────────────────────────────────────────────────────
# Supervisor / Aggregator
# ─────────────────────────────────────────────────────────────────────────────

SIGNAL_DIRECTION: Dict[SignalStrength, float] = {
    SignalStrength.STRONG_BULL: 1.0,
    SignalStrength.MILD_BULL: 0.6,
    SignalStrength.NEUTRAL: 0.0,
    SignalStrength.MILD_BEAR: -0.6,
    SignalStrength.STRONG_BEAR: -1.0,
}


class SwarmSupervisor:
    """
    Collects votes from all specialist agents and produces a SwarmConsensus.
    Runs agents concurrently to minimise latency.
    """

    def __init__(self) -> None:
        self.agents = build_swarm()
        self._is_evaluating = False
        self._evaluating_symbol: Optional[str] = None
        self._last_evaluated_at: Optional[datetime] = None

    @property
    def is_evaluating(self) -> bool:
        return self._is_evaluating

    @property
    def evaluating_symbol(self) -> Optional[str]:
        return self._evaluating_symbol

    @property
    def last_evaluated_at(self) -> Optional[datetime]:
        return self._last_evaluated_at

    def recently_active(self, seconds: float = 120.0) -> bool:
        if self._last_evaluated_at is None:
            return self._is_evaluating
        elapsed = (datetime.utcnow() - self._last_evaluated_at).total_seconds()
        return self._is_evaluating or elapsed < seconds

    async def evaluate(self, symbol: str) -> SwarmConsensus:
        """
        Gather all agent votes concurrently and compute weighted consensus.
        Returns a SwarmConsensus with trigger_trade=True/False.
        """
        self._is_evaluating = True
        self._evaluating_symbol = symbol
        try:
            # Fire all agents concurrently with a timeout guard
            tasks = [
                asyncio.wait_for(agent.analyze(symbol), timeout=15.0)
                for agent in self.agents
            ]
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            votes: List[AgentVote] = []
            for agent, result in zip(self.agents, raw_results):
                if isinstance(result, Exception):
                    logger.debug(f"[Supervisor] Agent {agent.agent_id} timed out or errored: {result}")
                else:
                    votes.append(result)

            logger.info(f"[Supervisor] Collected {len(votes)}/{len(self.agents)} votes")

            # Weighted aggregation
            total_weight = 0.0
            weighted_direction = 0.0
            volatility_scores: List[float] = []

            for vote in votes:
                agent_class_weight = next(
                    (a.VOTE_WEIGHT for a in self.agents if a.agent_id == vote.agent_id), 1.0
                )
                w = agent_class_weight * vote.confidence
                direction = SIGNAL_DIRECTION.get(vote.signal, 0.0)
                weighted_direction += direction * w
                total_weight += w

                if vote.role == AgentRole.VOLATILITY:
                    volatility_scores.append(vote.confidence * 100)

            avg_direction = weighted_direction / total_weight if total_weight > 0 else 0.0
            # avg_direction: -1 = full bear, +1 = full bull

            bull_score = (avg_direction + 1.0) / 2.0   # normalise to 0-1
            bear_score = 1.0 - bull_score

            # Leg weight proportional to conviction
            long_weight = bull_score
            short_weight = bear_score

            # Normalise weights to sum to 1
            total_w = long_weight + short_weight
            if total_w > 0:
                long_weight /= total_w
                short_weight /= total_w
            else:
                long_weight = short_weight = 0.5

            vol_pct = sum(volatility_scores) / len(volatility_scores) if volatility_scores else 50.0

            # Consensus score = how many agents agree with the majority direction
            majority_positive = avg_direction > 0
            agree_weight = sum(
                (a.VOTE_WEIGHT * v.confidence)
                for a, v in zip(self.agents, votes)
                if (SIGNAL_DIRECTION.get(v.signal, 0) > 0) == majority_positive
            )
            consensus_score = min(agree_weight / total_weight, 1.0) if total_weight > 0 else 0.5

            # Estimated expected move from volatility
            expected_move_pct = vol_pct * 0.1   # rough: 1 std-dev daily move proxy

            trigger = (
                consensus_score >= settings.min_consensus_score
                and vol_pct >= settings.min_volatility_percentile
            )

            consensus = SwarmConsensus(
                symbol=symbol,
                bull_score=round(bull_score, 4),
                bear_score=round(bear_score, 4),
                volatility_percentile=round(vol_pct, 2),
                expected_move_pct=round(expected_move_pct, 2),
                consensus_score=round(consensus_score, 4),
                trigger_trade=trigger,
                long_weight=round(long_weight, 4),
                short_weight=round(short_weight, 4),
                votes=votes,
            )

            logger.info(
                f"[Supervisor] Consensus for {symbol}: "
                f"bull={bull_score:.2f} bear={bear_score:.2f} "
                f"vol_pct={vol_pct:.1f} consensus={consensus_score:.2f} "
                f"trigger={trigger} weights={long_weight:.2f}/{short_weight:.2f}"
            )

            self._last_evaluated_at = datetime.utcnow()
            return consensus
        finally:
            self._is_evaluating = False
            self._evaluating_symbol = None
