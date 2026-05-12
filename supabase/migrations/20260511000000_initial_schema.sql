-- ═══════════════════════════════════════════════════════════════════════════════
-- DualAgentHedgeSystem — Initial PostgreSQL Schema
-- Created: 2026-05-11
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users & Auth ──────────────────────────────────────────────────────────────
-- Supabase handles auth.users; we extend with a profiles table

CREATE TABLE public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT UNIQUE,
    display_name TEXT,
    avatar_url TEXT,
    trading_api_key_encrypted TEXT,    -- encrypted exchange API key
    trading_api_secret_encrypted TEXT, -- encrypted exchange API secret
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, username)
    VALUES (NEW.id, NEW.raw_user_meta_data->>'username');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ── Trades ────────────────────────────────────────────────────────────────────

CREATE TABLE public.trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    qty NUMERIC NOT NULL,
    price NUMERIC,
    exchange TEXT,
    strategy TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
    pnl NUMERIC DEFAULT 0,
    fees NUMERIC DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX idx_trades_user ON public.trades(user_id);
CREATE INDEX idx_trades_symbol ON public.trades(symbol);
CREATE INDEX idx_trades_created ON public.trades(created_at DESC);

-- ── Positions ─────────────────────────────────────────────────────────────────

CREATE TABLE public.positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty NUMERIC NOT NULL DEFAULT 0,
    avg_entry_price NUMERIC NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC DEFAULT 0,
    realized_pnl NUMERIC DEFAULT 0,
    leverage NUMERIC DEFAULT 1,
    exchange TEXT,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

CREATE INDEX idx_positions_user ON public.positions(user_id);

-- ── Equity History ────────────────────────────────────────────────────────────

CREATE TABLE public.equity_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    total_equity NUMERIC NOT NULL DEFAULT 0,
    available_margin NUMERIC NOT NULL DEFAULT 0,
    used_margin NUMERIC NOT NULL DEFAULT 0,
    daily_pnl NUMERIC DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_equity_user ON public.equity_history(user_id);
CREATE INDEX idx_equity_created ON public.equity_history(created_at DESC);

-- ── Agent Votes ───────────────────────────────────────────────────────────────

CREATE TABLE public.agent_votes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    vote INT NOT NULL DEFAULT 0 CHECK (vote BETWEEN -1 AND 1),
    confidence NUMERIC NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_votes_user ON public.agent_votes(user_id);
CREATE INDEX idx_votes_agent ON public.agent_votes(agent_name);

-- ── Arbitrage Opportunities ───────────────────────────────────────────────────

CREATE TABLE public.arb_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pair TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    buy_price NUMERIC NOT NULL,
    sell_price NUMERIC NOT NULL,
    spread_pct NUMERIC NOT NULL,
    profit_estimate NUMERIC,
    executed BOOLEAN DEFAULT FALSE,
    execution_result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_arb_user ON public.arb_opportunities(user_id);
CREATE INDEX idx_arb_created ON public.arb_opportunities(created_at DESC);

-- ── System Settings ───────────────────────────────────────────────────────────

CREATE TABLE public.system_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, key)
);

CREATE INDEX idx_settings_user ON public.system_settings(user_id);

-- ── Custom Exchanges ──────────────────────────────────────────────────────────

CREATE TABLE public.custom_exchanges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    exchange_id TEXT NOT NULL,
    name TEXT NOT NULL,
    api_url TEXT NOT NULL,
    ws_url TEXT,
    auth_type TEXT NOT NULL DEFAULT 'api_key',
    credentials_encrypted JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, exchange_id)
);

CREATE INDEX idx_exchanges_user ON public.custom_exchanges(user_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- ROW LEVEL SECURITY (RLS) — Iron-Clad Per-User Isolation
-- ═══════════════════════════════════════════════════════════════════════════════

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equity_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.arb_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_exchanges ENABLE ROW LEVEL SECURITY;

-- ── Profiles ──────────────────────────────────────────────────────────────────
CREATE POLICY "Users can read own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id);

-- ── Trades ────────────────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own trades"
    ON public.trades FOR ALL
    USING (auth.uid() = user_id);

-- ── Positions ─────────────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own positions"
    ON public.positions FOR ALL
    USING (auth.uid() = user_id);

-- ── Equity ────────────────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own equity history"
    ON public.equity_history FOR ALL
    USING (auth.uid() = user_id);

-- ── Agent Votes ───────────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own agent votes"
    ON public.agent_votes FOR ALL
    USING (auth.uid() = user_id);

-- ── Arb Opportunities ─────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own arb opportunities"
    ON public.arb_opportunities FOR ALL
    USING (auth.uid() = user_id);

-- ── Settings ──────────────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own settings"
    ON public.system_settings FOR ALL
    USING (auth.uid() = user_id);

-- ── Custom Exchanges ──────────────────────────────────────────────────────────
CREATE POLICY "Users can CRUD own custom exchanges"
    ON public.custom_exchanges FOR ALL
    USING (auth.uid() = user_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- REALTIME (for WebSocket-like live updates)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER PUBLICATION supabase_realtime ADD TABLE public.trades;
ALTER PUBLICATION supabase_realtime ADD TABLE public.positions;
ALTER PUBLICATION supabase_realtime ADD TABLE public.equity_history;
ALTER PUBLICATION supabase_realtime ADD TABLE public.arb_opportunities;

-- ═══════════════════════════════════════════════════════════════════════════════
-- UPDATED_AT TRIGGER (auto-updates updated_at column)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_settings_updated_at
    BEFORE UPDATE ON public.system_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
