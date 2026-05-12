import { useQuery, useMutation } from '@tanstack/react-query'
import type {
  Trade, Agent, DefenseStatus, Analytics, SystemStatus,
  Settings, Position, MarketSnapshot, SwarmConsensus, ExchangeDepth,
  ExchangeBalance, ExchangePosition,
} from '@/types'

const API_BASE = '/api'

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('hedgeswarm_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...getAuthHeaders(),
      ...(options?.headers || {}),
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`HTTP ${res.status}: ${body || res.statusText}`)
  }
  return res.json()
}

export function useSystemStatus() {
  return useQuery<SystemStatus>({
    queryKey: ['status'],
    queryFn: () => fetchJson(`${API_BASE}/status`),
    retry: 2,
  })
}

export function useHealth() {
  return useQuery<{ status: string; engine_running: boolean; active_packages: number }>({
    queryKey: ['health'],
    queryFn: () => fetchJson(`${API_BASE}/health`),
    refetchInterval: 5000,
    retry: 2,
  })
}

export function useTrades(limit = 100) {
  return useQuery<{ trades: Trade[] }>({
    queryKey: ['trades', limit],
    queryFn: () => fetchJson(`${API_BASE}/trades?limit=${limit}`),
    retry: 2,
  })
}

export function usePositions() {
  return useQuery<{ positions: Position[] }>({
    queryKey: ['positions'],
    queryFn: () => fetchJson(`${API_BASE}/positions`),
    refetchInterval: 3000,
    retry: 2,
  })
}

export function useEquity() {
  return useQuery<{ equity_usdt: number; timestamp: string }>({
    queryKey: ['equity'],
    queryFn: () => fetchJson(`${API_BASE}/equity`),
    refetchInterval: 10000,
    retry: 2,
  })
}

export function useMarketSnapshot(symbol: string) {
  return useQuery<MarketSnapshot>({
    queryKey: ['market', symbol],
    queryFn: () => fetchJson(`${API_BASE}/market/snapshot?symbol=${encodeURIComponent(symbol)}`),
    refetchInterval: 5000,
    retry: 1,
    enabled: !!symbol,
  })
}

export function useAgents() {
  return useQuery<{ agents: Agent[] }>({
    queryKey: ['agents'],
    queryFn: () => fetchJson(`${API_BASE}/agents`),
    refetchInterval: 3000,
    retry: 2,
  })
}

export function useSwarmConsensus() {
  return useQuery<SwarmConsensus>({
    queryKey: ['swarm_consensus'],
    queryFn: () => fetchJson(`${API_BASE}/swarm/consensus`),
    refetchInterval: 3000,
    retry: 2,
  })
}

export function useExchangeDepth(symbol: string, exchange: string) {
  return useQuery<ExchangeDepth>({
    queryKey: ['depth', symbol, exchange],
    queryFn: () => fetchJson(`${API_BASE}/exchange/depth?symbol=${encodeURIComponent(symbol)}&exchange=${encodeURIComponent(exchange)}`),
    refetchInterval: 2000,
    retry: 1,
    enabled: !!symbol && !!exchange,
  })
}

export function useExchangeBalance(exchange: string, asset: string = 'USDT') {
  return useQuery<ExchangeBalance>({
    queryKey: ['balance', exchange, asset],
    queryFn: () => fetchJson(`${API_BASE}/exchange/balance?exchange=${encodeURIComponent(exchange)}&asset=${encodeURIComponent(asset)}`),
    refetchInterval: 5000,
    retry: 1,
    enabled: !!exchange,
  })
}

export function useExchangePositions(exchange: string, symbol?: string) {
  return useQuery<{ exchange: string; positions: ExchangePosition[] }>({
    queryKey: ['positions', exchange, symbol],
    queryFn: () => fetchJson(`${API_BASE}/exchange/positions?exchange=${encodeURIComponent(exchange)}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ''}`),
    refetchInterval: 3000,
    retry: 1,
    enabled: !!exchange,
  })
}

export function usePlaceOrder() {
  return useMutation({
    mutationFn: (order: {
      exchange: string
      symbol: string
      side: 'buy' | 'sell'
      amount: number
      type?: string
      leverage?: number
    }) => fetchJson(`${API_BASE}/exchange/order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(order),
    }),
  })
}

export function useDefense() {
  return useQuery<{ defense: DefenseStatus }>({
    queryKey: ['defense'],
    queryFn: () => fetchJson(`${API_BASE}/defense`),
    retry: 2,
  })
}

export function useAnalytics() {
  return useQuery<Analytics>({
    queryKey: ['analytics'],
    queryFn: () => fetchJson(`${API_BASE}/analytics`),
    retry: 2,
  })
}

export function useSettings() {
  return useQuery<Settings>({
    queryKey: ['settings'],
    queryFn: () => fetchJson(`${API_BASE}/settings`),
    retry: 2,
  })
}

export function useCommand() {
  return useMutation({
    mutationFn: (cmd: { command: string; payload?: object }) =>
      fetchJson(`${API_BASE}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cmd),
      }),
  })
}

export function usePortfolio(days = 30) {
  return useQuery<{
    equity_curve: { timestamp: string; equity: number; drawdown: number }[]
    monthly_returns: { month: string; pnl: number }[]
    current_equity: number
    max_drawdown: number
  }>({
    queryKey: ['portfolio', days],
    queryFn: () => fetchJson(`${API_BASE}/portfolio?days=${days}`),
    retry: 2,
  })
}

export function useAdvancedAnalytics() {
  return useQuery<{
    sharpe_ratio: number
    sortino_ratio: number
    max_drawdown_pct: number
    recovery_factor: number
    expectancy: number
    avg_trade: number
    best_trade: number
    worst_trade: number
    longest_win_streak: number
    longest_loss_streak: number
    current_streak_type: string | null
    current_streak: number
  }>({
    queryKey: ['analytics_advanced'],
    queryFn: () => fetchJson(`${API_BASE}/analytics/advanced`),
    retry: 2,
  })
}

export function useAgentAccuracy(days = 30) {
  return useQuery<{
    accuracy: { role: string; total_votes: number; correct_votes: number; accuracy_pct: number; avg_confidence: number }[]
    days: number
  }>({
    queryKey: ['agents_accuracy', days],
    queryFn: () => fetchJson(`${API_BASE}/agents/accuracy?days=${days}`),
    retry: 2,
  })
}

export function useRisk() {
  return useQuery<{
    equity: number
    total_exposure: number
    exposure_pct: number
    daily_drawdown_pct: number
    daily_halted: boolean
    max_drawdown_limit: number
    open_positions: number
    active_packages: number
  }>({
    queryKey: ['risk'],
    queryFn: () => fetchJson(`${API_BASE}/risk`),
    refetchInterval: 5000,
    retry: 2,
  })
}

export function useArbOpportunities(limit = 50, days = 0) {
  return useQuery<{ opportunities: import('@/types').ArbOpportunity[] }>({
    queryKey: ['arb_opportunities', limit, days],
    queryFn: () => fetchJson(`${API_BASE}/arbitrage/opportunities?limit=${limit}&days=${days}`),
    retry: 2,
  })
}

export function useArbLive() {
  return useQuery<{ opportunities: import('@/types').ArbOpportunity[]; stats: import('@/types').ArbStats; status: string }>({
    queryKey: ['arb_live'],
    queryFn: () => fetchJson(`${API_BASE}/arbitrage/live`),
    refetchInterval: 3000,
    retry: 2,
  })
}

export function useArbStats() {
  return useQuery<import('@/types').ArbStats>({
    queryKey: ['arb_stats'],
    queryFn: () => fetchJson(`${API_BASE}/arbitrage/stats`),
    refetchInterval: 5000,
    retry: 2,
  })
}

export function useUpdateSettings() {
  return useMutation({
    mutationFn: (payload: Partial<Settings>) =>
      fetchJson(`${API_BASE}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
  })
}

export function useTestExchange() {
  return useMutation<{
    status: string
    exchange: string
    testnet?: boolean
    markets?: number
    usdt_balance?: number
    detail?: string
  }, Error, {
    exchange_id: string
    api_key: string
    api_secret: string
    api_passphrase?: string
    testnet: boolean
  }>({
    mutationFn: (payload) =>
      fetchJson(`${API_BASE}/exchanges/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
  })
}

export function useArbControl() {
  const start = useMutation({
    mutationFn: () =>
      fetchJson(`${API_BASE}/arbitrage/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
  })
  const stop = useMutation({
    mutationFn: () =>
      fetchJson(`${API_BASE}/arbitrage/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
  })
  return { start, stop }
}

export function useCustomExchanges() {
  return useQuery<{ exchanges: { exchange_id: string; api_key: string; testnet: boolean; created_at: string }[] }>({
    queryKey: ['custom_exchanges'],
    queryFn: () => fetchJson(`${API_BASE}/exchanges`),
    retry: 2,
  })
}

export function useAddExchange() {
  return useMutation({
    mutationFn: (payload: { exchange_id: string; api_key: string; api_secret: string; api_passphrase?: string; testnet: boolean }) =>
      fetchJson(`${API_BASE}/exchanges`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
  })
}

export function useDeleteExchange() {
  return useMutation({
    mutationFn: (exchange_id: string) =>
      fetchJson(`${API_BASE}/exchanges/${exchange_id}`, {
        method: 'DELETE',
      }),
  })
}

export function useAuth() {
  const login = useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      fetchJson(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      }),
  })

  const me = useQuery<{ username: string }>({
    queryKey: ['me'],
    queryFn: () => fetchJson(`${API_BASE}/auth/me`),
    retry: false,
  })

  return { login, me }
}
