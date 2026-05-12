// Verified: Interface matches all properties returned by app_fullstack.py endpoints
// Last audited: 2026-05-11 against DefenseStatus dataclass, TradeRecord ORM, LegState model

export interface Trade {
  package_id: string
  symbol: string
  status: string
  pnl_usdt: number
  risk_budget: number
  pnl_pct: number
  close_reason: string
  created_at: string
  closed_at?: string
  long_exchange: string
  short_exchange: string
  long_pnl: number
  short_pnl: number
  // Leg size & entry detail (v2.3)
  long_qty?: number
  short_qty?: number
  long_notional?: number
  short_notional?: number
  long_entry?: number
  short_entry?: number
  long_leverage?: number
  short_leverage?: number
  funding_paid?: number
}

export interface Position {
  package_id: string
  symbol: string
  side: string
  exchange: string
  entry_price: number
  current_price: number
  quantity: number
  leverage: number
  notional: number
  unrealized_pnl: number
  stop_loss: number
  take_profit: number
}

export interface MarketSnapshot {
  symbol: string
  bid: number
  ask: number
  last: number
  mark_price: number
  index_price: number
  open_interest: number
  funding_rate: number
  volume_24h: number
  change_24h_pct: number
  timestamp: string
}

export interface Agent {
  agent_id: string
  role: string
  weight: number
  task: string
  status: string
}

export interface DefenseStatus {
  active: boolean
  circuit_broken: boolean
  bull_score: number
  active_exchange: string
  total_events: number
  rotations_today: number
  stealth_splits_today: number
  unresolved_events: number
  last_action: string | null
  events: DefenseEvent[]
}

export interface DefenseEvent {
  time: string
  exchange: string
  symbol: string
  type: string
  severity: number
  action: string
}

export interface Analytics {
  total_pnl: number
  win_count: number
  loss_count: number
  total_closed: number
  win_rate: number
  avg_win: number
  avg_loss: number
  profit_factor: number
}

export interface SystemStatus {
  status: string
  engine_running: boolean
  active_packages: number
  mode: string
  timestamp: string
  watchlist: string[]
  paper_trading: boolean
}

export interface AgentRoleConfig {
  SENTIMENT: number
  TWITTER_SENTIMENT: number
  TECHNICAL: number
  VOLATILITY: number
  ONCHAIN: number
  FUNDING: number
  ORDERFLOW: number
  MACRO: number
  NEWS: number
  REFLECTION: number
}

export interface Settings {
  paper_trading: boolean
  watchlist: string[]
  max_risk_per_package_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  trailing_stop_pct: number
  default_leverage: number
  min_consensus_score: number
  min_volatility_percentile: number
  signal_refresh_seconds: number
  defense_enabled: boolean
  defense_bull_run_threshold: number
  max_daily_drawdown_pct: number
  max_concurrent_packages: number
  funding_rate_threshold: number
  rebalance_interval_min: number
  // Exchange config
  long_exchange_id: string
  short_exchange_id: string
  same_exchange_hedge_mode: boolean
  bybit_testnet: boolean
  okx_testnet: boolean
  binance_testnet: boolean
  bybit_api_key: string
  okx_api_key: string
  binance_api_key: string
  // Agent config
  agent_role_config: AgentRoleConfig | null
}

export interface ArbOpportunity {
  id?: string
  strategy: string
  symbol: string
  buy_exchange: string
  sell_exchange: string
  buy_price: number
  sell_price: number
  spread_pct: number
  fees_pct: number
  net_profit_pct: number
  size_usdt: number
  net_profit_usdt: number
  executed: boolean
  timestamp: string
  // Transfer arb fields
  withdrawal_fee?: number
  network_fee_usdt?: number
  deposit_fee?: number
  withdrawal_time_min?: number
  deposit_time_min?: number
  min_withdraw_amount?: number
  withdraw_enabled?: boolean
  deposit_enabled?: boolean
  net_gain_coins?: number
  net_gain_usdt?: number
}

export interface ArbStats {
  status: string
  is_running: boolean
  scans: number
  opportunities_found: number
  executed: number
  total_profit_usdt: number
}

export interface SwarmConsensus {
  symbol: string
  direction: 'bullish' | 'bearish' | 'neutral'
  confidence: number
  bull_score: number
  bear_score: number
  consensus_score: number
  trigger_trade: boolean
  evaluated_at: string
}

export interface ExchangeTrade {
  price: number
  amount: number
  side: 'buy' | 'sell'
  timestamp: string
}

export interface ExchangeDepth {
  symbol: string
  exchange: string
  bids: [number, number][]
  asks: [number, number][]
  trades: ExchangeTrade[]
  timestamp: string
}

export interface ExchangeBalance {
  exchange: string
  asset: string
  free: number
  used: number
  total: number
}

export interface ExchangePosition {
  symbol: string
  side: string
  contracts: number
  entry_price: number
  mark_price: number
  unrealized_pnl: number
  leverage: number
  notional: number
}

export interface WSMessage {
  type: 'init' | 'update' | 'pong' | 'command_queued'
  timestamp?: string
  trades?: Trade[]
  defense?: DefenseStatus | null
  agents?: Agent[]
  positions?: Position[]
  equity?: number
  consensus?: SwarmConsensus | null
}
