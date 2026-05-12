# DualAgentHedgeSystem

A full-stack crypto hedge trading platform with dual AI agents, real-time arbitrage detection, portfolio analytics, and multi-exchange support.

## Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + Vite + Tailwind CSS + Recharts + RainbowKit |
| **Backend** | FastAPI + LangGraph + SQLite |
| **Auth** | Self-hosted JWT (local username/password + Google/GitHub/Facebook OAuth) |
| **Database** | SQLite with per-user isolation (user_id on all tables) |
| **Wallet** | RainbowKit + wagmi (MetaMask, WalletConnect, Coinbase Wallet) |

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/mitchvac/DualAgentHedgeSystem.git
cd DualAgentHedgeSystem

# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required env vars:
```bash
JWT_SECRET_KEY=your-secret-key
ADMIN_USER=admin
ADMIN_PASSWORD=admin
```

Optional — for social login:
```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
FACEBOOK_CLIENT_ID=...
FACEBOOK_CLIENT_SECRET=...
```

### 3. Run Locally

```bash
# Terminal 1 — Backend
python app_fullstack.py

# Terminal 2 — Frontend
cd frontend && npm run dev
```

## Features

- **Dual-Agent Trading Engine** — Up/Down directional agents with confidence scoring
- **Arbitrage Scanner** — Cross-exchange opportunity detection
- **Portfolio & Analytics** — Real-time PnL, equity curves, risk metrics
- **Agent Leaderboard** — Performance ranking with voting
- **Risk Dashboard** — VaR, drawdown, leverage monitoring
- **Wallet Connect** — Connect MetaMask/WalletConnect to view balances
- **Social Login** — Google, GitHub, Facebook OAuth
- **Per-User Data Isolation** — Every table has `user_id`, all queries are scoped

## Auth

The app uses **self-hosted JWT auth**:
- Username/password registration & login
- Google, GitHub, Facebook OAuth (optional)
- JWT tokens stored in `localStorage`
- Iron-clad row-level isolation on all data via `user_id`

## Deployment

See [docs/DEPLOY.md](docs/DEPLOY.md) for Vercel + backend deployment.

## License

MIT
