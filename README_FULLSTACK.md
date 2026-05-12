# HedgeSwarm — Full-Stack Dual-Agent Composite Hedge System

A production-ready, full-stack crypto trading application featuring a **React + TypeScript** frontend, **FastAPI** backend, and a **100-agent swarm** trading engine with dual-position hedging.

**Zero mock data. Every number on the dashboard comes from live exchange APIs or the trading engine.**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                │
│  React 18 · TypeScript · Vite · Tailwind CSS · Recharts        │
│  Auth (JWT) · WebSocket Real-Time · Dark Theme                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP / WS (same process)
┌────────────────────────▼────────────────────────────────────────┐
│              UNIFIED BACKEND (main_fullstack.py)                │
│  FastAPI · JWT Auth · REST API · WebSocket Broadcasts          │
│  Static File Serving · Live Exchange Data · SQLite DB          │
├────────────────────────┬────────────────────────────────────────┤
│  │ Shared Memory Access (same asyncio event loop)              │
│  ▼                                                             │
│  Orchestrator · UpAgent · DownAgent · 100-Agent Swarm         │
│  Risk Manager · Defense Swarm · CCXT Exchanges · ChromaDB     │
└─────────────────────────────────────────────────────────────────┘
```

**Key design decision:** The trading engine and API server run in the **same process** sharing the same `asyncio` event loop. This means:
- The API reads **live position data** directly from `orchestrator.active_packages`
- The API reads **live equity** directly from exchange balance APIs
- The API reads **live agent status** directly from the running swarm
- **Zero polling delay, zero mock data, zero Redis required**

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.12+**
- **Node.js 20+**
- **Docker & Docker Compose** (optional)

### 1. Clone & Configure

```bash
cd DualAgentHedgeSystem
cp .env.example .env
# Edit .env with your exchange API keys
```

### 2. Development Mode

```bash
chmod +x start-dev.sh
./start-dev.sh
```

| Service | URL | Description |
|---------|-----|-------------|
| React Frontend | http://localhost:3000 | Modern trading dashboard |
| Unified API + Engine | http://localhost:3003 | Backend + live trading engine |
| Streamlit (legacy) | http://localhost:8501 | Original dashboard |

**Login:** `admin` / `admin` (change in `.env`)

### 3. Production (Docker)

```bash
# Build frontend first
cd frontend && npm install && npm run build && cd ..

# Deploy everything
docker-compose up --build -d
```

| Service | URL | Description |
|---------|-----|-------------|
| Frontend (nginx) | http://localhost | Production UI |
| API + Engine | http://localhost:3003 | Unified backend |
| Streamlit (legacy) | http://localhost:8501 | Original dashboard |

---

## 📡 Real-Time Data Flow

```
Exchange APIs (Bybit/OKX/Binance)
         │
         ▼
┌─────────────────┐
│  Orchestrator   │ ← runs dual-agent hedge logic
│  (same process) │
└────────┬────────┘
         │ shared memory
         ▼
┌─────────────────┐     WebSocket      ┌─────────────────┐
│   FastAPI App   │ ─────────────────→ │  React Frontend │
│  (broadcast)    │   (5s interval)    │  (live UI)      │
└─────────────────┘                    └─────────────────┘
```

**What gets broadcast live:**
- `trades` — from SQLite `memory_store`
- `positions` — from `orchestrator.active_packages` (live PnL, entry/mark prices)
- `equity` — from exchange `fetch_balance()`
- `defense` — from `DefenseCoordinator`
- `agents` — from `SwarmSupervisor` with real working/idle status

---

## 📁 Project Structure

```
DualAgentHedgeSystem/
├── frontend/                          # React + TypeScript frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── KPICard.tsx
│   │   │   ├── PnLChart.tsx           # Real cumulative PnL
│   │   │   ├── TradeTable.tsx         # Real trade history
│   │   │   ├── PositionsPanel.tsx     # LIVE open positions
│   │   │   ├── WatchlistPrices.tsx    # LIVE exchange prices
│   │   │   ├── AgentGrid.tsx          # Real 100-agent roster
│   │   │   ├── DefensePanel.tsx       # Real defense status
│   │   │   ├── Layout.tsx
│   │   │   ├── Sidebar.tsx
│   │   │   └── Header.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx          # Real-time overview
│   │   │   ├── Trades.tsx             # Filterable history + CSV export
│   │   │   ├── Agents.tsx             # Swarm control + filters
│   │   │   ├── Settings.tsx           # System config viewer
│   │   │   └── Login.tsx              # JWT auth
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # Real-time WS hook
│   │   │   └── useApi.ts              # React Query hooks
│   │   ├── store/
│   │   │   └── authStore.ts           # Zustand auth state
│   │   └── types/
│   │       └── index.ts               # TypeScript interfaces
│   ├── package.json
│   ├── vite.config.ts
│   └── dist/                          # Production build
│
├── app_fullstack.py                   # Enhanced FastAPI (ZERO mocks)
├── main_fullstack.py                  # Unified entry: engine + API
├── main.py                            # Standalone engine entry
│
├── orchestrator.py                    # LangGraph workflow (modified: global ref)
├── up_agent.py / down_agent.py        # Dual agents (untouched)
├── exchange_client.py                 # CCXT wrapper (untouched)
├── risk_manager.py                    # Risk engine (untouched)
├── memory_store.py                    # SQLite + ChromaDB (untouched)
├── swarm_agents.py                    # 100-agent swarm (untouched)
├── defense_swarm.py                   # Anti-bot layer (untouched)
├── config.py                          # System config (untouched)
├── models.py                          # Pydantic models (untouched)
│
├── requirements.txt                   # Python deps (+jwt, +passlib)
├── Dockerfile                         # Python backend image
├── Dockerfile.frontend                # React + nginx image
├── docker-compose.yml                 # Full stack orchestration
├── nginx.conf                         # Reverse proxy config
├── start-dev.sh                       # One-command dev startup
├── .env.example                       # Environment template
└── README_FULLSTACK.md                # This file
```

---

## 🔐 Authentication

The full-stack frontend uses **JWT Bearer tokens**:

- **Default login:** `admin` / `admin`
- **Token expiry:** 24 hours
- **Storage:** localStorage

Configure in `.env`:
```bash
ADMIN_USER=admin
ADMIN_PASSWORD=your-secure-password
JWT_SECRET_KEY=your-random-32-char-secret
```

---

## 📡 API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | OAuth2 password login |
| GET | `/api/auth/me` | Current user info |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Engine health, active package count |
| GET | `/api/status` | System status & mode |
| GET | `/api/settings` | System configuration |

### Trading (LIVE data)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trades` | Trade history from SQLite |
| GET | `/api/positions` | **LIVE** open positions from engine |
| GET | `/api/equity` | **LIVE** account balance from exchange |
| GET | `/api/market/snapshot/{symbol}` | **LIVE** market data from exchange |
| POST | `/api/command` | Queue command to engine |

### Agents & Defense
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | 100-agent roster with live status |
| GET | `/api/defense` | Defense swarm status |
| GET | `/api/analytics` | Win rate, PnL, profit factor |

### Real-Time
| Protocol | Endpoint | Description |
|----------|----------|-------------|
| WebSocket | `/ws` | Live trades, positions, equity, defense, agents |

---

## 🎨 Frontend Features

- **Live Positions Panel** — Entry/mark prices, unrealized PnL, stop loss, leverage per leg
- **Live Watchlist** — Real bid/ask, 24h change, volume, funding rate from exchange
- **Engine Status Indicator** — Shows if the orchestrator is actually running
- **Dark Theme** — Professional trading UI
- **Real-Time Dashboard** — WebSocket-connected KPI cards, PnL charts
- **Trade History** — Filterable table with CSV export
- **Agent Swarm** — Live grid with working/idle status
- **Defense Panel** — Anti-bot defense monitoring

---

## ⚙️ Configuration

All settings via environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `PAPER_TRADING` | `true` | Dry-run mode |
| `ADMIN_USER` | `admin` | Dashboard login |
| `ADMIN_PASSWORD` | `admin` | Dashboard password |
| `JWT_SECRET_KEY` | — | JWT signing secret |
| `BYBIT_API_KEY` | — | Bybit credentials |
| `OKX_API_KEY` | — | OKX credentials |
| `OPENAI_API_KEY` | — | LLM provider |
| `DEFENSE_ENABLED` | `true` | Anti-bot layer |

---

## 🧪 Testing

```bash
# Backend
pytest

# Frontend (from ./frontend)
npm run lint
npm run build
```

---

## 📄 License

MIT — HedgeSwarm v2.1
