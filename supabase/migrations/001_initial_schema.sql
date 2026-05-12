-- DualAgentHedgeSystem Supabase Schema
-- Iron-clad RLS: every table has RLS enabled with user_id policies
-- Run this in Supabase SQL Editor after creating the project

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────────────────────────
-- USERS (managed by Supabase Auth, but we reference auth.uid())
-- ─────────────────────────────────────────────────────────────────────────────

-- Profiles table extends Supabase Auth users
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    avatar_url TEXT,
    paper_trading BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TRADES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.trades (
    package_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting',
    combined_pnl DOUBLE PRECISION DEFAULT 0.0,
    risk_budget DOUBLE PRECISION DEFAULT 0.0,
    close_reason TEXT DEFAULT '',
    consensus_json TEXT DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    closed_at TIMESTAMPTZ,
    notes TEXT DEFAULT '[]',
    -- Leg detail
    long_exchange TEXT,
    short_exchange TEXT,
    long_pnl DOUBLE PRECISION DEFAULT 0.0,
    short_pnl DOUBLE PRECISION DEFAULT 0.0,
    long_qty DOUBLE PRECISION,
    short_qty DOUBLE PRECISION,
    long_notional DOUBLE PRECISION,
    short_notional DOUBLE PRECISION,
    long_entry DOUBLE PRECISION,
    short_entry DOUBLE PRECISION,
    long_leverage INTEGER,
    short_leverage INTEGER,
    funding_paid DOUBLE PRECISION DEFAULT 0.0
);

CREATE INDEX idx_trades_user_id ON public.trades(user_id);
CREATE INDEX idx_trades_symbol ON public.trades(symbol);
CREATE INDEX idx_trades_created_at ON public.trades(created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- EQUITY HISTORY
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.equity_history (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    equity DOUBLE PRECISION DEFAULT 0.0,
    pnl_today DOUBLE PRECISION DEFAULT 0.0,
    drawdown_pct DOUBLE PRECISION DEFAULT 0.0,
    timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_equity_user_id ON public.equity_history(user_id);
CREATE INDEX idx_equity_timestamp ON public.equity_history(timestamp DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- AGENT VOTES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.agent_votes (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence DOUBLE PRECISION DEFAULT 0.0,
    was_correct BOOLEAN,
    timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_votes_user_id ON public.agent_votes(user_id);
CREATE INDEX idx_votes_agent_id ON public.agent_votes(agent_id);
CREATE INDEX idx_votes_symbol ON public.agent_votes(symbol);

-- ─────────────────────────────────────────────────────────────────────────────
-- ARBITRAGE OPPORTUNITIES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.arb_opportunities (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    buy_price DOUBLE PRECISION DEFAULT 0.0,
    sell_price DOUBLE PRECISION DEFAULT 0.0,
    spread_pct DOUBLE PRECISION DEFAULT 0.0,
    fees_pct DOUBLE PRECISION DEFAULT 0.0,
    net_profit_pct DOUBLE PRECISION DEFAULT 0.0,
    size_usdt DOUBLE PRECISION DEFAULT 0.0,
    net_profit_usdt DOUBLE PRECISION DEFAULT 0.0,
    funding_rate DOUBLE PRECISION,
    withdrawal_fee DOUBLE PRECISION,
    network_fee_usdt DOUBLE PRECISION,
    deposit_fee DOUBLE PRECISION,
    withdrawal_time_min INTEGER,
    deposit_time_min INTEGER,
    min_withdraw_amount DOUBLE PRECISION,
    withdraw_enabled BOOLEAN DEFAULT true,
    deposit_enabled BOOLEAN DEFAULT true,
    net_gain_coins DOUBLE PRECISION,
    net_gain_usdt DOUBLE PRECISION,
    executed BOOLEAN DEFAULT false,
    timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_arb_user_id ON public.arb_opportunities(user_id);
CREATE INDEX idx_arb_symbol ON public.arb_opportunities(symbol);

-- ─────────────────────────────────────────────────────────────────────────────
-- SYSTEM SETTINGS (per-user)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_settings (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, key)
);

CREATE INDEX idx_settings_user_id ON public.user_settings(user_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- CUSTOM EXCHANGES (per-user)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.custom_exchanges (
    exchange_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    api_key TEXT DEFAULT '',
    api_secret TEXT DEFAULT '',
    api_passphrase TEXT DEFAULT '',
    testnet BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (exchange_id, user_id)
);

CREATE INDEX idx_exchanges_user_id ON public.custom_exchanges(user_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- ROW LEVEL SECURITY POLICIES — IRON CLAD
-- Prime directive: users can ONLY see their own data
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable RLS on all tables
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equity_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.arb_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.custom_exchanges ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owners (critical!)
ALTER TABLE public.profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE public.trades FORCE ROW LEVEL SECURITY;
ALTER TABLE public.equity_history FORCE ROW LEVEL SECURITY;
ALTER TABLE public.agent_votes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.arb_opportunities FORCE ROW LEVEL SECURITY;
ALTER TABLE public.user_settings FORCE ROW LEVEL SECURITY;
ALTER TABLE public.custom_exchanges FORCE ROW LEVEL SECURITY;

-- Profiles: users see only their own profile
CREATE POLICY "profiles_isolation" ON public.profiles
    FOR ALL USING (auth.uid() = id);

-- Trades: users see only their own trades
CREATE POLICY "trades_isolation" ON public.trades
    FOR ALL USING (auth.uid() = user_id);

-- Equity: users see only their own equity snapshots
CREATE POLICY "equity_isolation" ON public.equity_history
    FOR ALL USING (auth.uid() = user_id);

-- Agent votes: users see only their own votes
CREATE POLICY "votes_isolation" ON public.agent_votes
    FOR ALL USING (auth.uid() = user_id);

-- Arb opportunities: users see only their own
CREATE POLICY "arb_isolation" ON public.arb_opportunities
    FOR ALL USING (auth.uid() = user_id);

-- Settings: users see only their own settings
CREATE POLICY "settings_isolation" ON public.user_settings
    FOR ALL USING (auth.uid() = user_id);

-- Exchanges: users see only their own exchanges
CREATE POLICY "exchanges_isolation" ON public.custom_exchanges
    FOR ALL USING (auth.uid() = user_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────────────

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, username, paper_trading)
    VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'username', NEW.email), true);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger on auth.users insert
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Function to prune old equity snapshots (keep 90 days)
CREATE OR REPLACE FUNCTION public.prune_old_equity()
RETURNS void AS $$
BEGIN
    DELETE FROM public.equity_history
    WHERE timestamp < now() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
