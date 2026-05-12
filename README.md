# DualAgentHedgeSystem

A full-stack crypto hedge trading platform with dual AI agents, real-time arbitrage detection, and portfolio analytics.

## Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 + Vite + Tailwind CSS + Recharts |
| **Backend** | FastAPI + LangGraph + SQLite (PostgreSQL migration in progress) |
| **Auth** | Supabase Auth (email/password + GitHub OAuth) |
| **Database** | Supabase PostgreSQL with RLS |
| **Deploy** | Vercel (frontend) + Railway/Render/Fly.io (backend) |

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
# Edit .env with your Supabase credentials
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
- **Iron-Clad RLS** — Every table has `user_id` + PostgreSQL RLS policies

## Deployment

See [docs/DEPLOY.md](docs/DEPLOY.md) for Vercel + Supabase deployment.

## Auth

The app uses **Supabase Auth**:
- Email/password registration & login
- GitHub OAuth (configure in Supabase dashboard)
- JWT tokens automatically refreshed
- Iron-clad row-level security on all data

## License

MIT
