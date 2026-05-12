# 🤖 Dual-Agent Composite Hedge Trading System

> **Python 3.12 · LangGraph · CCXT · CrewAI · ChromaDB · Streamlit**

A self-sufficient, 24/7 autonomous trading system that opens **one composite hedge trade per coin** — a simultaneous long + short on perpetual futures — managed by a 100-agent AI swarm.

---

## Table of Contents

1. [System Architecture](#architecture)
2. [File Structure](#file-structure)
3. [Quick Start](#quick-start)
4. [Testing One BTC Composite Trade](#test-btc-trade)
5. [Configuration Reference](#configuration)
6. [Agent Roles & Swarm Design](#swarm-design)
7. [Risk Management Rules](#risk-management)
8. [Multi-Exchange Setup](#multi-exchange)
9. [Running the Dashboard](#dashboard)
10. [Extending the System](#extending)
11. [Production Checklist](#production)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Orchestrator (LangGraph)                      │
│  IDLE → SCAN → SWARM CONSENSUS → RISK GATE → EXECUTE → MONITOR     │
└────────────────────────────┬────────────────────────────────────────┘
                             │
           ┌─────────────────┴─────────────────┐
           │         100-Agent Swarm            │
           │  Supervisor aggregates all votes   │
           │                                   │
           │  Sentiment (15) Technical (20)     │
           │  Volatility (10) OnChain (15)      │
           │  Funding (10)   OrderFlow (15)     │
           │  Macro (5)      News (5)           │
           │  Reflection (5)                   │
           └─────────────────┬─────────────────┘
                             │
                    SwarmConsensus
                    (bull/bear score,
                     vol percentile,
                     leg weights)
                             │
           ┌─────────────────┴──────────────────┐
           │                                    │
    ┌──────▼──────┐                    ┌────────▼──────┐
    │  Up-Agent   │                    │  Down-Agent   │
    │  LONG leg   │                    │  SHORT leg    │
    │  Bybit      │                    │  OKX          │
    └─────────────┘                    └───────────────┘
           │                                    │
           └──────────────┬─────────────────────┘
                          │
                  TradePackage
                  (shared risk budget,
                   unified P&L,
                   joint stop/kill logic)
                          │
                   Risk Manager
                   (position sizing,
                    daily drawdown CB,
                    trailing stops,
                    rebalance engine)
                          │
                  Memory Store
                  (SQLite + ChromaDB)
```

---

## File Structure

```
hedge-system/
├── main.py                # Live trading entry point
├── backtest.py            # Paper-trading & historical backtest
├── dashboard.py           # Streamlit live dashboard
│
├── orchestrator.py        # Master LangGraph workflow controller
├── up_agent.py            # Bullish specialist (long leg)
├── down_agent.py          # Bearish specialist (short leg)
├── swarm_agents.py        # 100-agent swarm (all specialist teams)
│
├── exchange_client.py     # Async CCXT wrapper (multi-exchange)
├── risk_manager.py        # Position sizing, circuit breakers, trailing stops
├── memory_store.py        # SQLite + ChromaDB persistence
├── models.py              # Shared Pydantic data models
├── config.py              # Settings from environment variables
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── hedge_system_env_example.txt  # Rename to .env and fill in keys
```

---

## Quick Start

### 1. Clone & Install

```bash
git clone <your-repo>
cd hedge-system

# Python 3.12+ required
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp hedge_system_env_example.txt .env
# Edit .env — fill in your API keys
# Leave PAPER_TRADING=true until you're ready for live trading
```

### 3. Run Paper Trading

```bash
python main.py --paper
```

### 4. Run Backtest (30 days BTC)

```bash
python backtest.py --mode backtest --symbol BTC/USDT:USDT --days 30
```

### 5. Launch Dashboard

```bash
streamlit run dashboard.py
# Open http://localhost:8501
```

### 6. Docker (recommended for production)

```bash
docker compose up --build -d
# Engine: hedge-engine
# Dashboard: http://localhost:8501
```

---

## Test One BTC Composite Trade

This walk-through fires a **single composite BTC trade** end-to-end in paper mode.

```bash
# 1. Ensure PAPER_TRADING=true in .env
# 2. Set watchlist to BTC only:
#    WATCHLIST=BTC/USDT:USDT

python backtest.py --mode paper
```

You should see logs like:

```
10:22:01 | INFO     | [Orchestrator] Starting swarm evaluation for BTC/USDT:USDT (100 agents)
10:22:04 | INFO     | [Supervisor] Consensus for BTC/USDT:USDT: bull=0.61 bear=0.39
           vol_pct=73.2 consensus=0.67 trigger=True weights=0.61/0.39
10:22:04 | INFO     | [Risk] Trade approved
10:22:04 | INFO     | [Execution] Opening composite package: LONG BTC/USDT:USDT on bybit
           + SHORT BTC/USDT:USDT on okx
10:22:04 | INFO     | [PaperTrade] MARKET LONG 0.001234 BTC/USDT:USDT on bybit
10:22:04 | INFO     | [PaperTrade] MARKET SHORT 0.000789 BTC/USDT:USDT on okx
10:22:04 | INFO     | [Orchestrator] Package abc123 ACTIVE for BTC/USDT:USDT
```

To force a trade even in low-volatility conditions for testing:

```python
# In config.py, temporarily set:
min_consensus_score: float = 0.0
min_volatility_percentile: float = 0.0
```

---

## Configuration

All settings live in `.env`. Key parameters:

| Variable | Default | Description |
|---|---|---|
| `PAPER_TRADING` | `true` | Set `false` for live orders |
| `LONG_EXCHANGE_ID` | `bybit` | Exchange for long leg |
| `SHORT_EXCHANGE_ID` | `okx` | Exchange for short leg |
| `SAME_EXCHANGE_HEDGE_MODE` | `false` | Both legs on same exchange |
| `MAX_RISK_PER_PACKAGE_PCT` | `0.5` | % of equity per package |
| `MAX_DAILY_DRAWDOWN_PCT` | `3.0` | Circuit-breaker threshold |
| `DEFAULT_LEVERAGE` | `5` | Starting leverage |
| `STOP_LOSS_PCT` | `2.0` | Per-leg stop loss |
| `TAKE_PROFIT_PCT` | `4.0` | Per-leg take profit |
| `TRAILING_STOP_PCT` | `1.5` | Trailing stop from peak |
| `MIN_CONSENSUS_SCORE` | `0.65` | Minimum swarm agreement |
| `MIN_VOLATILITY_PERCENTILE` | `60.0` | Min vol to trigger trade |
| `SIGNAL_REFRESH_SECONDS` | `30` | Monitor tick interval |

---

## Swarm Design

The 100 agents are divided into specialist teams, each contributing a **weighted vote**:

| Team | Count | Weight | Signal Source |
|---|---|---|---|
| Sentiment | 15 | 0.6–0.8 | LunarCrush, Twitter |
| Technical | 20 | 1.2 | RSI, MACD, EMA, Bollinger, multi-TF |
| Volatility | 10 | 1.0 | Realised vol percentile |
| On-Chain | 15 | 1.1 | Glassnode (SOPR, netflows, MVRV) |
| Funding Rate | 10 | 1.0 | Live funding from CCXT |
| Order Flow | 15 | 0.9 | Order book imbalance |
| Macro | 5 | 0.7 | Fear & Greed, DXY |
| News | 5 | 0.6 | CryptoPanic headlines |
| Reflection | 5 | 0.9 | ChromaDB historical memory |

**Consensus formula:**
```
weighted_direction = Σ(vote_weight × confidence × direction_score)
bull_score = (weighted_direction + 1) / 2
leg_weights = bull_score / (bull_score + bear_score)
trigger = consensus_score ≥ 0.65 AND vol_percentile ≥ 60
```

---

## Risk Management

The system has **5 layers of protection**:

1. **Position sizing**: Kelly-adjusted (half-Kelly), hard-capped at `MAX_RISK_PER_PACKAGE_PCT`
2. **Per-leg stop loss**: `STOP_LOSS_PCT` from entry (market order on breach)
3. **Per-leg take profit**: `TAKE_PROFIT_PCT` from entry
4. **Package-level hard stop**: Kill if combined loss ≥ entire risk budget
5. **Daily circuit breaker**: Halt all new trades if daily drawdown ≥ `MAX_DAILY_DRAWDOWN_PCT`
6. **Trailing stop**: `TRAILING_STOP_PCT` from peak combined PnL
7. **Max concurrent packages**: Never more than 3 packages open simultaneously

---

## Multi-Exchange Setup

### Two Exchanges (default)
- **Long leg**: Bybit (configured via `BYBIT_API_*`)
- **Short leg**: OKX (configured via `OKX_API_*`)
- Both legs open simultaneously using `asyncio.gather()`

### Single Exchange (hedge mode)
```env
SAME_EXCHANGE_HEDGE_MODE=true
LONG_EXCHANGE_ID=bybit
SHORT_EXCHANGE_ID=bybit
```
This enables Bybit's "hedge mode" (dual-position) automatically.

### Adding a third exchange
1. Add credentials to `.env` (see `BINANCE_API_*` example)
2. Add `get_exchange_kwargs()` case in `config.py`
3. Route specific coins to different exchanges via config

---

## Dashboard

```bash
streamlit run dashboard.py
```

Features:
- 📈 Cumulative PnL equity curve
- 🗳️ Agent vote radar chart by team
- 📋 Live trade package table (status, P&L, close reason)
- ⚡ KPI metrics: win rate, total trades, active packages
- 🔄 Auto-refreshes every 10 seconds

---

## Extending the System

### Add a new specialist agent

```python
# In swarm_agents.py
class MyNewAgent(BaseSpecialistAgent):
    VOTE_WEIGHT = 1.0
    ROLE = AgentRole.TECHNICAL

    async def analyze(self, symbol: str) -> AgentVote:
        # your signal logic here
        return self._make_vote(SignalStrength.MILD_BULL, 0.7, "my signal")

# In build_swarm():
agents.append(MyNewAgent())
```

### Integrate Grok / Claude
```python
# In config.py, set:
default_llm_model = "claude-3-5-sonnet-20241022"
# or for Grok:
default_llm_model = "grok-2"
grok_api_key = "xai-..."
```

### Add a new exchange

```python
# In config.py — add to get_exchange_kwargs():
elif ex == "deribit":
    return {
        "apiKey": self.deribit_api_key,
        "secret": self.deribit_api_secret,
        "options": {"defaultType": "future"},
    }
```

---

## Production Checklist

- [ ] Test in paper mode for ≥ 2 weeks before going live
- [ ] Set `PAPER_TRADING=false` only after validating all API connections
- [ ] Start with `DEFAULT_LEVERAGE=2` and `MAX_RISK_PER_PACKAGE_PCT=0.2`
- [ ] Enable testnet on all exchanges first (`*_TESTNET=true`)
- [ ] Monitor the Streamlit dashboard daily
- [ ] Set up log rotation and alerting on `data/system.log`
- [ ] Back up `data/trades.db` and `data/chroma/` regularly
- [ ] Never commit your `.env` to version control
- [ ] Run behind a VPN / dedicated server for 24/7 uptime

---

## Disclaimer

This software is for **educational and research purposes**. Crypto trading carries substantial financial risk. The "composite hedge" strategy does **not guarantee profits** — both legs can lose simultaneously in extreme market conditions. Always use proper position sizing and never risk more than you can afford to lose.
