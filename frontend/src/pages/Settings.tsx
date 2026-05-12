import { useState, useEffect } from 'react'
import {
  Save, RotateCcw, Shield, AlertTriangle, CheckCircle, Zap,
  TrendingUp, TrendingDown, Scale, RefreshCw, Server, Bot, Plus,
  HelpCircle,
} from 'lucide-react'
import WatchlistInput from '@/components/WatchlistInput'
import {
  useSettings, useUpdateSettings, useTestExchange,
  useCustomExchanges, useAddExchange, useDeleteExchange,
} from '@/hooks/useApi'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import type { AgentRoleConfig } from '@/types'
import Tooltip from '@/components/Tooltip'

// Verified: Interface matches all properties returned by /api/settings
interface SettingsForm {
  max_risk_per_package_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  trailing_stop_pct: number
  default_leverage: number
  min_consensus_score: number
  defense_enabled: boolean
  defense_bull_run_threshold: number
  signal_refresh_seconds: number
  watchlist: string
  max_daily_drawdown_pct: number
  max_concurrent_packages: number
  funding_rate_threshold: number
  rebalance_interval_min: number
  // Trading mode
  paper_trading: boolean
  // Exchange
  long_exchange_id: string
  short_exchange_id: string
  same_exchange_hedge_mode: boolean
  bybit_testnet: boolean
  okx_testnet: boolean
  binance_testnet: boolean
  bybit_api_key: string
  bybit_api_secret: string
  okx_api_key: string
  okx_api_secret: string
  okx_api_passphrase: string
  binance_api_key: string
  binance_api_secret: string
  // Agent config
  agent_role_config: AgentRoleConfig
}

interface PresetConfig {
  name: string
  icon: React.ReactNode
  description: string
  color: string
  values: Partial<SettingsForm>
}

const PRESETS: PresetConfig[] = [
  {
    name: 'Conservative',
    icon: <Shield className="w-4 h-4" />,
    description: 'Lowest drawdown, steady compounding',
    color: 'emerald',
    values: {
      max_risk_per_package_pct: 0.75,
      stop_loss_pct: 2.5,
      take_profit_pct: 7.5,
      trailing_stop_pct: 1.2,
      default_leverage: 3,
      min_consensus_score: 0.72,
      defense_bull_run_threshold: 0.75,
      max_daily_drawdown_pct: 3.5,
      max_concurrent_packages: 4,
      funding_rate_threshold: 0.05,
      rebalance_interval_min: 15,
      signal_refresh_seconds: 45,
    },
  },
  {
    name: 'Balanced',
    icon: <Scale className="w-4 h-4" />,
    description: 'Best Sharpe, highest all-around',
    color: 'blue',
    values: {
      max_risk_per_package_pct: 1.0,
      stop_loss_pct: 3.0,
      take_profit_pct: 8.0,
      trailing_stop_pct: 1.5,
      default_leverage: 4,
      min_consensus_score: 0.68,
      defense_bull_run_threshold: 0.70,
      max_daily_drawdown_pct: 5.0,
      max_concurrent_packages: 6,
      funding_rate_threshold: 0.03,
      rebalance_interval_min: 15,
      signal_refresh_seconds: 30,
    },
  },
  {
    name: 'Aggressive',
    icon: <Zap className="w-4 h-4" />,
    description: 'Higher returns, more variance',
    color: 'orange',
    values: {
      max_risk_per_package_pct: 1.5,
      stop_loss_pct: 4.0,
      take_profit_pct: 10.0,
      trailing_stop_pct: 2.0,
      default_leverage: 5,
      min_consensus_score: 0.62,
      defense_bull_run_threshold: 0.65,
      max_daily_drawdown_pct: 7.0,
      max_concurrent_packages: 8,
      funding_rate_threshold: 0.0,
      rebalance_interval_min: 10,
      signal_refresh_seconds: 20,
    },
  },
  {
    name: 'Bull Market',
    icon: <TrendingUp className="w-4 h-4" />,
    description: 'Lean long when bull run triggers',
    color: 'purple',
    values: {
      max_risk_per_package_pct: 1.25,
      stop_loss_pct: 3.5,
      take_profit_pct: 9.0,
      trailing_stop_pct: 1.8,
      default_leverage: 5,
      min_consensus_score: 0.65,
      defense_bull_run_threshold: 0.80,
      max_daily_drawdown_pct: 6.0,
      max_concurrent_packages: 7,
      funding_rate_threshold: 0.02,
      rebalance_interval_min: 12,
      signal_refresh_seconds: 25,
    },
  },
  {
    name: 'High Vol / Bear',
    icon: <TrendingDown className="w-4 h-4" />,
    description: 'Protect capital in crashes',
    color: 'red',
    values: {
      max_risk_per_package_pct: 0.5,
      stop_loss_pct: 2.0,
      take_profit_pct: 6.0,
      trailing_stop_pct: 1.0,
      default_leverage: 2,
      min_consensus_score: 0.75,
      defense_bull_run_threshold: 0.85,
      max_daily_drawdown_pct: 2.5,
      max_concurrent_packages: 3,
      funding_rate_threshold: 0.05,
      rebalance_interval_min: 20,
      signal_refresh_seconds: 60,
    },
  },
]

const DEFAULT_AGENT_COUNTS: AgentRoleConfig = {
  SENTIMENT: 15,
  TWITTER_SENTIMENT: 5,
  TECHNICAL: 20,
  VOLATILITY: 10,
  ONCHAIN: 15,
  FUNDING: 10,
  ORDERFLOW: 15,
  MACRO: 5,
  NEWS: 5,
  REFLECTION: 5,
}

interface FieldDef {
  key: keyof SettingsForm
  label: string
  type: 'number' | 'boolean' | 'select' | 'text'
  min?: number
  max?: number
  step?: number
  options?: string[]
  tooltip?: string
}

const RISK_FIELDS: FieldDef[] = [
  { key: 'max_risk_per_package_pct', label: 'Max Risk Per Package (%)', type: 'number', min: 0.1, max: 10, step: 0.1, tooltip: '% of account per trade' },
  { key: 'stop_loss_pct', label: 'Stop Loss (%)', type: 'number', min: 0.5, max: 20, step: 0.5, tooltip: 'Per-leg stop loss' },
  { key: 'take_profit_pct', label: 'Take Profit (%)', type: 'number', min: 0.5, max: 50, step: 0.5, tooltip: 'Per-leg take profit' },
  { key: 'trailing_stop_pct', label: 'Trailing Stop (%)', type: 'number', min: 0.1, max: 10, step: 0.1, tooltip: 'Trailing stop distance' },
  { key: 'default_leverage', label: 'Default Leverage', type: 'number', min: 1, max: 100, step: 1, tooltip: 'Leverage per leg' },
  { key: 'min_consensus_score', label: 'Min Consensus Score', type: 'number', min: 0, max: 1, step: 0.05, tooltip: 'Swarm agreement threshold (0-1)' },
]

const SAFETY_FIELDS: FieldDef[] = [
  { key: 'max_daily_drawdown_pct', label: 'Max Daily Drawdown (%)', type: 'number', min: 0.5, max: 20, step: 0.5, tooltip: 'Hard kill-switch — pauses all trading' },
  { key: 'max_concurrent_packages', label: 'Max Concurrent Packages', type: 'number', min: 1, max: 20, step: 1, tooltip: 'Max open composite trades' },
  { key: 'funding_rate_threshold', label: 'Funding Rate Threshold (%)', type: 'number', min: 0, max: 1, step: 0.01, tooltip: '±% filter for perp funding' },
  { key: 'rebalance_interval_min', label: 'Rebalance Interval (min)', type: 'number', min: 1, max: 120, step: 1, tooltip: 'Swarm re-evaluation cycle' },
]

const DEFENSE_FIELDS: FieldDef[] = [
  { key: 'defense_enabled', label: 'Defense Enabled', type: 'boolean' },
  { key: 'defense_bull_run_threshold', label: 'Bull Run Threshold', type: 'number', min: 0, max: 1, step: 0.05, tooltip: 'Triggers aggressive defense mode' },
  { key: 'signal_refresh_seconds', label: 'Signal Refresh (s)', type: 'number', min: 5, max: 300, step: 5, tooltip: 'Market scan interval' },
]

const EXCHANGE_FIELDS: FieldDef[] = [
  { key: 'long_exchange_id', label: 'Long Exchange', type: 'select', options: ['bybit', 'okx', 'binance'], tooltip: 'Exchange for Up-Agent leg' },
  { key: 'short_exchange_id', label: 'Short Exchange', type: 'select', options: ['bybit', 'okx', 'binance'], tooltip: 'Exchange for Down-Agent leg' },
  { key: 'same_exchange_hedge_mode', label: 'Same-Exchange Hedge Mode', type: 'boolean', tooltip: 'Both legs on same exchange' },
  { key: 'bybit_testnet', label: 'Bybit Testnet', type: 'boolean' },
  { key: 'okx_testnet', label: 'OKX Testnet', type: 'boolean' },
  { key: 'binance_testnet', label: 'Binance Testnet', type: 'boolean' },
]

const AGENT_ROLES: { key: keyof AgentRoleConfig; label: string }[] = [
  { key: 'SENTIMENT', label: 'Sentiment' },
  { key: 'TWITTER_SENTIMENT', label: 'Twitter Sentiment' },
  { key: 'TECHNICAL', label: 'Technical' },
  { key: 'VOLATILITY', label: 'Volatility' },
  { key: 'ONCHAIN', label: 'OnChain' },
  { key: 'FUNDING', label: 'Funding' },
  { key: 'ORDERFLOW', label: 'OrderFlow' },
  { key: 'MACRO', label: 'Macro' },
  { key: 'NEWS', label: 'News' },
  { key: 'REFLECTION', label: 'Reflection' },
]

const colorMap: Record<string, string> = {
  emerald: 'border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400',
  blue: 'border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400',
  orange: 'border-orange-500/30 bg-orange-500/10 hover:bg-orange-500/20 text-orange-400',
  purple: 'border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400',
  red: 'border-red-500/30 bg-red-500/10 hover:bg-red-500/20 text-red-400',
}

const activeColorMap: Record<string, string> = {
  emerald: 'ring-2 ring-emerald-500/50 bg-emerald-500/20',
  blue: 'ring-2 ring-blue-500/50 bg-blue-500/20',
  orange: 'ring-2 ring-orange-500/50 bg-orange-500/20',
  purple: 'ring-2 ring-purple-500/50 bg-purple-500/20',
  red: 'ring-2 ring-red-500/50 bg-red-500/20',
}

function ExchangeCard({
  exchange,
  label,
  form,
  onChange,
}: {
  exchange: string
  label: string
  form: Partial<SettingsForm>
  onChange: (key: keyof SettingsForm, value: any) => void
}) {
  const testExchange = useTestExchange()
  const [testResult, setTestResult] = useState<{status: string; detail?: string; markets?: number; usdt_balance?: number} | null>(null)

  const testnetKey = `${exchange}_testnet` as keyof SettingsForm
  const apiKeyKey = `${exchange}_api_key` as keyof SettingsForm
  const apiSecretKey = `${exchange}_api_secret` as keyof SettingsForm
  const passphraseKey = `${exchange}_api_passphrase` as keyof SettingsForm

  const isTestnet = !!form[testnetKey]
  const apiKey = String(form[apiKeyKey] || '')
  const apiSecret = String(form[apiSecretKey] || '')
  const passphrase = String((form as any)[passphraseKey] || '')

  const handleTest = async () => {
    setTestResult(null)
    try {
      const result = await testExchange.mutateAsync({
        exchange_id: exchange,
        api_key: apiKey,
        api_secret: apiSecret,
        api_passphrase: passphrase,
        testnet: isTestnet,
      })
      setTestResult(result)
    } catch (err: any) {
      setTestResult({ status: 'error', detail: err.message })
    }
  }

  const statusColors: Record<string, string> = {
    connected: 'text-emerald-400',
    auth_failed: 'text-red-400',
    network_error: 'text-orange-400',
    error: 'text-red-400',
  }

  return (
    <div className="bg-[#0a0a0f] rounded-xl border border-[#2a2a35] p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-white">{label}</span>
          <button
            type="button"
            onClick={() => onChange(testnetKey, !isTestnet)}
            className={cn(
              'px-2 py-0.5 rounded text-[10px] font-medium transition-all border',
              isTestnet
                ? 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
            )}
          >
            {isTestnet ? 'Testnet' : 'Live'}
          </button>
        </div>
        <button
          onClick={handleTest}
          disabled={testExchange.isPending || !apiKey || !apiSecret}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-[#16161f] border border-[#2a2a35] rounded-lg text-xs text-gray-300 hover:border-blue-500/30 hover:text-blue-400 transition-all disabled:opacity-40"
        >
          <RefreshCw className={cn('w-3 h-3', testExchange.isPending && 'animate-spin')} />
          {testExchange.isPending ? 'Testing...' : 'Test Connection'}
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          type="password"
          value={apiKey}
          onChange={(e) => onChange(apiKeyKey, e.target.value)}
          placeholder="API Key"
          className="w-full bg-[#16161f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all"
        />
        <input
          type="password"
          value={apiSecret}
          onChange={(e) => onChange(apiSecretKey, e.target.value)}
          placeholder="API Secret"
          className="w-full bg-[#16161f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all"
        />
      </div>
      {exchange === 'okx' && (
        <input
          type="password"
          value={passphrase}
          onChange={(e) => onChange(passphraseKey as keyof SettingsForm, e.target.value)}
          placeholder="Passphrase (if required)"
          className="w-full bg-[#16161f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-all"
        />
      )}

      {testResult && (
        <div className={cn(
          'text-xs px-3 py-2 rounded-lg border',
          testResult.status === 'connected'
            ? 'bg-emerald-500/5 border-emerald-500/20 text-emerald-400'
            : 'bg-red-500/5 border-red-500/20 text-red-400'
        )}>
          <span className={cn('font-semibold', statusColors[testResult.status] || 'text-gray-400')}>
            {testResult.status === 'connected' ? 'Connected' : 'Failed'}
          </span>
          {testResult.markets !== undefined && (
            <span className="text-gray-400 ml-2">· {testResult.markets} markets</span>
          )}
          {testResult.usdt_balance !== undefined && (
            <span className="text-gray-400 ml-2">· {testResult.usdt_balance} USDT</span>
          )}
          {testResult.detail && (
            <div className="text-gray-500 mt-0.5">{testResult.detail}</div>
          )}
        </div>
      )}
    </div>
  )
}

function ExchangeConfigSection({
  form,
  onChange,
  onSave,
  isSaving,
}: {
  form: Partial<SettingsForm>
  onChange: (key: keyof SettingsForm, value: any) => void
  onSave: () => void
  isSaving: boolean
}) {
  const [showAddModal, setShowAddModal] = useState(false)
  const [newEx, setNewEx] = useState({ exchange_id: '', api_key: '', api_secret: '', api_passphrase: '', testnet: true })
  const { data: customExchanges, refetch } = useCustomExchanges()
  const addEx = useAddExchange()
  const delEx = useDeleteExchange()

  const handleAdd = async () => {
    if (!newEx.exchange_id.trim()) return
    try {
      await addEx.mutateAsync({
        exchange_id: newEx.exchange_id.trim().toLowerCase(),
        api_key: newEx.api_key,
        api_secret: newEx.api_secret,
        api_passphrase: newEx.api_passphrase,
        testnet: newEx.testnet,
      })
      setShowAddModal(false)
      setNewEx({ exchange_id: '', api_key: '', api_secret: '', api_passphrase: '', testnet: true })
      refetch()
    } catch (err: any) {
      alert(err.message || 'Failed to add exchange')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(`Delete ${id}?`)) return
    try {
      await delEx.mutateAsync(id)
      refetch()
    } catch (err: any) {
      alert(err.message || 'Failed to delete exchange')
    }
  }

  const allExchanges = ['bybit', 'okx', 'binance', ...(customExchanges?.exchanges?.map((e) => e.exchange_id) || [])]

  return (
    <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5 space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Server className="w-5 h-5 text-blue-400" />
          <h3 className="text-sm font-semibold text-gray-200">Exchange Configuration</h3>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 rounded-lg text-xs text-blue-400 hover:bg-blue-500/20 transition-all"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Exchange
        </button>
      </div>

      {/* Exchange Assignment */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        <div className="bg-[#0a0a0f] rounded-xl border border-[#2a2a35] p-3">
          <div className="text-xs text-gray-500 mb-1">Long Exchange</div>
          <select
            value={form.long_exchange_id || 'bybit'}
            onChange={(e) => onChange('long_exchange_id', e.target.value)}
            className="w-full bg-[#16161f] border border-[#2a2a35] rounded-lg px-2.5 py-1.5 text-sm text-white focus:outline-none focus:border-orange-500/50"
          >
            {allExchanges.map((ex) => (
              <option key={ex} value={ex}>{ex.toUpperCase()}</option>
            ))}
          </select>
        </div>
        <div className="bg-[#0a0a0f] rounded-xl border border-[#2a2a35] p-3">
          <div className="text-xs text-gray-500 mb-1">Short Exchange</div>
          <select
            value={form.short_exchange_id || 'okx'}
            onChange={(e) => onChange('short_exchange_id', e.target.value)}
            className="w-full bg-[#16161f] border border-[#2a2a35] rounded-lg px-2.5 py-1.5 text-sm text-white focus:outline-none focus:border-orange-500/50"
          >
            {allExchanges.map((ex) => (
              <option key={ex} value={ex}>{ex.toUpperCase()}</option>
            ))}
          </select>
        </div>
        <div className="bg-[#0a0a0f] rounded-xl border border-[#2a2a35] p-3 flex items-center justify-between">
          <div>
            <div className="text-xs text-gray-500">Hedge Mode</div>
            <div className="text-xs text-gray-400 mt-0.5">Same exchange</div>
          </div>
          <button
            type="button"
            onClick={() => onChange('same_exchange_hedge_mode', !form.same_exchange_hedge_mode)}
            className={cn(
              'px-3 py-1 rounded-lg text-xs font-medium transition-all',
              form.same_exchange_hedge_mode
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'bg-red-500/20 text-red-400 border border-red-500/30'
            )}
          >
            {form.same_exchange_hedge_mode ? 'Yes' : 'No'}
          </button>
        </div>
      </div>

      {/* Per-exchange cards */}
      <ExchangeCard exchange="bybit" label="Bybit" form={form} onChange={onChange} />
      <ExchangeCard exchange="okx" label="OKX" form={form} onChange={onChange} />
      <ExchangeCard exchange="binance" label="Binance" form={form} onChange={onChange} />
      {customExchanges?.exchanges?.map((ex) => (
        <div key={ex.exchange_id} className="bg-[#0a0a0f] rounded-xl border border-[#2a2a35] p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-3">
              <span className="text-sm font-semibold text-white">{ex.exchange_id.toUpperCase()}</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20">Custom</span>
            </div>
            <button
              onClick={() => handleDelete(ex.exchange_id)}
              className="text-xs text-red-400 hover:text-red-300 transition-colors"
            >
              Remove
            </button>
          </div>
          <div className="text-xs text-gray-500">API Key: {ex.api_key || 'Not set'} · Testnet: {ex.testnet ? 'Yes' : 'No'}</div>
        </div>
      ))}

      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={onSave}
          disabled={isSaving}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl text-sm font-medium text-white hover:from-blue-400 hover:to-blue-500 transition-all shadow-lg shadow-blue-500/20"
        >
          <Save className="w-4 h-4" />
          {isSaving ? 'Saving...' : 'Save Exchange Settings'}
        </button>
      </div>

      {/* Add Exchange Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6 w-full max-w-md space-y-4">
            <h3 className="text-lg font-bold text-white">Add New Exchange</h3>
            <p className="text-xs text-gray-500">Enter any CCXT-supported exchange ID (e.g. kucoin, gateio, kraken, mexc)</p>
            <input
              type="text"
              value={newEx.exchange_id}
              onChange={(e) => setNewEx((prev) => ({ ...prev, exchange_id: e.target.value }))}
              placeholder="exchange_id (e.g. kucoin)"
              className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                type="password"
                value={newEx.api_key}
                onChange={(e) => setNewEx((prev) => ({ ...prev, api_key: e.target.value }))}
                placeholder="API Key"
                className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
              />
              <input
                type="password"
                value={newEx.api_secret}
                onChange={(e) => setNewEx((prev) => ({ ...prev, api_secret: e.target.value }))}
                placeholder="API Secret"
                className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
              />
            </div>
            <input
              type="password"
              value={newEx.api_passphrase}
              onChange={(e) => setNewEx((prev) => ({ ...prev, api_passphrase: e.target.value }))}
              placeholder="Passphrase (if required)"
              className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50"
            />
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setNewEx((prev) => ({ ...prev, testnet: !prev.testnet }))}
                className={cn(
                  'px-3 py-1 rounded-lg text-xs font-medium transition-all',
                  newEx.testnet
                    ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                )}
              >
                {newEx.testnet ? 'Testnet' : 'Live'}
              </button>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleAdd}
                disabled={addEx.isPending || !newEx.exchange_id.trim()}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl text-sm font-medium text-white hover:from-blue-400 hover:to-blue-500 transition-all disabled:opacity-50"
              >
                {addEx.isPending ? 'Adding...' : 'Add Exchange'}
              </button>
              <button
                onClick={() => setShowAddModal(false)}
                className="flex-1 px-4 py-2 bg-[#0a0a0f] border border-[#2a2a35] rounded-xl text-sm text-gray-300 hover:border-gray-600 transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Settings() {
  const { data: settings, isLoading } = useSettings()
  const updateSettings = useUpdateSettings()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Partial<SettingsForm>>({})
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [activePreset, setActivePreset] = useState<string | null>(null)

  useEffect(() => {
    if (settings) {
      setForm({
        max_risk_per_package_pct: settings.max_risk_per_package_pct,
        stop_loss_pct: settings.stop_loss_pct,
        take_profit_pct: settings.take_profit_pct,
        trailing_stop_pct: settings.trailing_stop_pct,
        default_leverage: settings.default_leverage,
        min_consensus_score: settings.min_consensus_score,
        defense_enabled: settings.defense_enabled,
        defense_bull_run_threshold: settings.defense_bull_run_threshold,
        signal_refresh_seconds: settings.signal_refresh_seconds,
        watchlist: settings.watchlist?.join(', ') || 'BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT',
        max_daily_drawdown_pct: settings.max_daily_drawdown_pct,
        max_concurrent_packages: settings.max_concurrent_packages,
        funding_rate_threshold: settings.funding_rate_threshold,
        rebalance_interval_min: settings.rebalance_interval_min,
        long_exchange_id: settings.long_exchange_id,
        short_exchange_id: settings.short_exchange_id,
        same_exchange_hedge_mode: settings.same_exchange_hedge_mode,
        paper_trading: settings.paper_trading ?? true,
        bybit_testnet: settings.bybit_testnet,
        okx_testnet: settings.okx_testnet,
        binance_testnet: settings.binance_testnet,
        bybit_api_key: '',
        bybit_api_secret: '',
        okx_api_key: '',
        okx_api_secret: '',
        okx_api_passphrase: '',
        binance_api_key: '',
        binance_api_secret: '',
        agent_role_config: settings.agent_role_config || { ...DEFAULT_AGENT_COUNTS },
      })
    }
  }, [settings])

  const applyPreset = (preset: PresetConfig) => {
    setForm((prev) => ({ ...prev, ...preset.values }))
    setActivePreset(preset.name)
    setSaved(false)
    setError('')
  }

  const handleChange = (key: keyof SettingsForm, value: any) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
    setError('')
  }

  const handleAgentCountChange = (role: keyof AgentRoleConfig, value: number) => {
    setForm((prev) => ({
      ...prev,
      agent_role_config: {
        ...(prev.agent_role_config || DEFAULT_AGENT_COUNTS),
        [role]: Math.max(0, Math.min(50, value)),
      },
    }))
    setSaved(false)
    setError('')
  }

  const handleSave = async () => {
    setError('')
    try {
      const payload: Record<string, any> = {}
      const allFields: FieldDef[] = [...RISK_FIELDS, ...SAFETY_FIELDS, ...DEFENSE_FIELDS, ...EXCHANGE_FIELDS]
      allFields.forEach((f) => {
        const val = form[f.key]
        if (val === undefined) return
        if (f.type === 'boolean') {
          payload[f.key] = !!val
        } else if (f.type === 'number') {
          payload[f.key] = parseFloat(val as any)
        } else {
          payload[f.key] = val
        }
      })
      if (form.watchlist !== undefined) {
        payload.watchlist = (form.watchlist as string).split(',').map((s) => s.trim()).filter(Boolean)
      }
      // API keys (only send if non-empty)
      ;['bybit_api_key', 'bybit_api_secret', 'okx_api_key', 'okx_api_secret', 'okx_api_passphrase', 'binance_api_key', 'binance_api_secret'].forEach((k) => {
        const val = (form as any)[k]
        if (val && String(val).trim().length > 0) {
          payload[k] = String(val).trim()
        }
      })
      // Trading mode
      if (form.paper_trading !== undefined) {
        payload.paper_trading = !!form.paper_trading
      }
      // Agent config
      if (form.agent_role_config) {
        payload.agent_role_config = form.agent_role_config
      }

      await updateSettings.mutateAsync(payload)
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      queryClient.invalidateQueries({ queryKey: ['status'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to save settings')
    }
  }

  const handleReset = () => {
    if (!settings) return
    setForm({
      max_risk_per_package_pct: settings.max_risk_per_package_pct,
      stop_loss_pct: settings.stop_loss_pct,
      take_profit_pct: settings.take_profit_pct,
      trailing_stop_pct: settings.trailing_stop_pct,
      default_leverage: settings.default_leverage,
      min_consensus_score: settings.min_consensus_score,
      defense_enabled: settings.defense_enabled,
      defense_bull_run_threshold: settings.defense_bull_run_threshold,
      signal_refresh_seconds: settings.signal_refresh_seconds,
      watchlist: settings.watchlist?.join(', ') || '',
      max_daily_drawdown_pct: settings.max_daily_drawdown_pct,
      max_concurrent_packages: settings.max_concurrent_packages,
      funding_rate_threshold: settings.funding_rate_threshold,
      rebalance_interval_min: settings.rebalance_interval_min,
      long_exchange_id: settings.long_exchange_id,
      short_exchange_id: settings.short_exchange_id,
      same_exchange_hedge_mode: settings.same_exchange_hedge_mode,
      paper_trading: settings.paper_trading ?? true,
      bybit_testnet: settings.bybit_testnet,
      okx_testnet: settings.okx_testnet,
      binance_testnet: settings.binance_testnet,
      bybit_api_key: '',
      bybit_api_secret: '',
      okx_api_key: '',
      okx_api_secret: '',
      okx_api_passphrase: '',
      binance_api_key: '',
      binance_api_secret: '',
      agent_role_config: settings.agent_role_config || { ...DEFAULT_AGENT_COUNTS },
    })
    setActivePreset(null)
    setSaved(false)
    setError('')
  }

  const handleRestartEngine = () => {
    // In a real app this would call an API endpoint to restart
    setError('Engine restart requires manual restart of the server process.')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        Loading settings...
      </div>
    )
  }

  const renderField = (field: FieldDef) => {
    const value = form[field.key]
    if (field.type === 'boolean') {
      return (
        <button
          type="button"
          onClick={() => handleChange(field.key, !value)}
          className={cn(
            'px-3 py-1 rounded-lg text-xs font-medium transition-all',
            value
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-red-500/20 text-red-400 border border-red-500/30'
          )}
        >
          {value ? 'Yes' : 'No'}
        </button>
      )
    }
    if (field.type === 'select') {
      return (
        <select
          value={String(value ?? '')}
          onChange={(e) => handleChange(field.key, e.target.value)}
          className="w-32 bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-2.5 py-1 text-sm text-white focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20 transition-all"
        >
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }
    return (
      <div className="flex items-center gap-2" title={field.tooltip}>
        <input
          type="number"
          min={field.min}
          max={field.max}
          step={field.step}
          value={(value as string | number) ?? ''}
          onChange={(e) => handleChange(field.key, e.target.value)}
          className="w-24 bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-2.5 py-1 text-sm text-white text-right focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20 transition-all"
        />
      </div>
    )
  }

  const agentConfig = form.agent_role_config || DEFAULT_AGENT_COUNTS
  // TWITTER_SENTIMENT is a subset of SENTIMENT (not additive), so exclude from total
  const totalAgents = Object.entries(agentConfig).reduce((sum, [key, val]) => {
    if (key === 'TWITTER_SENTIMENT') return sum
    return sum + (val as number)
  }, 0)

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h2 className="text-xl font-bold text-white">System Settings</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Pick a preset or manually configure trading parameters
        </p>
      </div>

      {/* Trading Mode Toggle */}
      <div className={cn(
        'rounded-2xl border p-5 flex items-center justify-between transition-all',
        form.paper_trading
          ? 'bg-emerald-500/5 border-emerald-500/20'
          : 'bg-red-500/5 border-red-500/20'
      )}>
        <div className="flex items-center gap-4">
          <div className={cn(
            'w-12 h-12 rounded-xl flex items-center justify-center text-xl',
            form.paper_trading ? 'bg-emerald-500/10' : 'bg-red-500/10'
          )}>
            {form.paper_trading ? '📝' : '🔴'}
          </div>
          <div>
            <div className="text-sm font-semibold text-white">Trading Mode</div>
            <div className={cn(
              'text-lg font-bold',
              form.paper_trading ? 'text-emerald-400' : 'text-red-400'
            )}>
              {form.paper_trading ? 'PAPER TRADING' : 'LIVE TRADING'}
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              {form.paper_trading
                ? 'Simulated trades — no real money at risk'
                : '⚠️ REAL orders will be sent to exchanges. API keys required.'}
            </p>
          </div>
        </div>
        <button
          onClick={() => handleChange('paper_trading', !form.paper_trading)}
          className={cn(
            'relative w-16 h-8 rounded-full transition-all duration-300',
            form.paper_trading ? 'bg-emerald-500' : 'bg-red-500'
          )}
        >
          <div className={cn(
            'absolute top-1 w-6 h-6 rounded-full bg-white shadow-md transition-all duration-300',
            form.paper_trading ? 'left-1' : 'left-9'
          )} />
        </button>
      </div>

      {/* Presets */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {PRESETS.map((preset) => (
          <button
            key={preset.name}
            onClick={() => applyPreset(preset)}
            className={cn(
              'flex flex-col items-center gap-2 p-3 rounded-xl border text-sm font-medium transition-all',
              colorMap[preset.color],
              activePreset === preset.name && activeColorMap[preset.color]
            )}
          >
            {preset.icon}
            <span>{preset.name}</span>
            <span className="text-[10px] opacity-70 font-normal text-center leading-tight">
              {preset.description}
            </span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Risk Parameters */}
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-5 h-5 text-orange-400" />
            <h3 className="text-sm font-semibold text-gray-200">Risk Parameters</h3>
          </div>
          <div className="space-y-3">
            {RISK_FIELDS.map((field) => (
              <div key={field.key} className="flex items-center justify-between py-2 border-b border-[#1f1f2e]">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm text-gray-400">{field.label}</span>
                  {field.tooltip && (
                    <Tooltip content={field.tooltip}>
                      <HelpCircle className="w-3 h-3 text-gray-600 hover:text-gray-400 cursor-help" />
                    </Tooltip>
                  )}
                </div>
                {renderField(field)}
              </div>
            ))}
          </div>
        </div>

        {/* Safety & Limits */}
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Shield className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-semibold text-gray-200">Safety & Limits</h3>
          </div>
          <div className="space-y-3">
            {SAFETY_FIELDS.map((field) => (
              <div key={field.key} className="flex items-center justify-between py-2 border-b border-[#1f1f2e]">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm text-gray-400">{field.label}</span>
                  {field.tooltip && (
                    <Tooltip content={field.tooltip}>
                      <HelpCircle className="w-3 h-3 text-gray-600 hover:text-gray-400 cursor-help" />
                    </Tooltip>
                  )}
                </div>
                {renderField(field)}
              </div>
            ))}
          </div>

          <div className="pt-2">
            <WatchlistInput
              value={form.watchlist || ''}
              onChange={(val) => handleChange('watchlist', val)}
            />
          </div>
        </div>

        {/* Defense Swarm */}
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-5 h-5 text-yellow-400" />
            <h3 className="text-sm font-semibold text-gray-200">Defense Swarm</h3>
          </div>
          <div className="space-y-3">
            {DEFENSE_FIELDS.map((field) => (
              <div key={field.key} className="flex items-center justify-between py-2 border-b border-[#1f1f2e]">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm text-gray-400">{field.label}</span>
                  {field.tooltip && (
                    <Tooltip content={field.tooltip}>
                      <HelpCircle className="w-3 h-3 text-gray-600 hover:text-gray-400 cursor-help" />
                    </Tooltip>
                  )}
                </div>
                {renderField(field)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Exchange Configuration */}
      <ExchangeConfigSection
        form={form}
        onChange={handleChange}
        onSave={handleSave}
        isSaving={updateSettings.isPending}
      />

      {/* Agent Configuration */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-purple-400" />
            <h3 className="text-sm font-semibold text-gray-200">Agent Swarm Configuration</h3>
          </div>
          <span className="text-xs text-gray-500">{totalAgents} total agents</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {AGENT_ROLES.map((role) => (
            <div key={role.key} className="bg-[#0a0a0f] rounded-xl border border-[#2a2a35] p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-400">{role.label}</span>
                <span className="text-xs font-bold text-white">{agentConfig[role.key] || 0}</span>
              </div>
              <input
                type="range"
                min={0}
                max={30}
                step={1}
                value={agentConfig[role.key] || 0}
                onChange={(e) => handleAgentCountChange(role.key, parseInt(e.target.value))}
                className="w-full h-1.5 bg-[#2a2a35] rounded-lg appearance-none cursor-pointer accent-orange-500"
              />
            </div>
          ))}
        </div>

        <button
          onClick={handleRestartEngine}
          className="flex items-center gap-2 px-4 py-2 bg-[#0a0a0f] border border-[#2a2a35] rounded-xl text-sm text-gray-400 hover:text-orange-400 hover:border-orange-500/30 transition-all"
        >
          <RefreshCw className="w-4 h-4" />
          Restart Engine to Apply Agent Changes
        </button>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={handleSave}
          disabled={updateSettings.isPending}
          className={cn(
            'flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all shadow-lg',
            saved
              ? 'bg-emerald-500 text-white shadow-emerald-500/20'
              : 'bg-gradient-to-r from-orange-500 to-orange-600 text-white hover:from-orange-400 hover:to-orange-500 shadow-orange-500/20'
          )}
        >
          {saved ? <CheckCircle className="w-4 h-4" /> : <Save className="w-4 h-4" />}
          {updateSettings.isPending ? 'Saving...' : saved ? 'Saved!' : 'Apply Changes'}
        </button>
        <button
          onClick={handleReset}
          className="flex items-center gap-2 px-5 py-2.5 bg-[#16161f] border border-[#2a2a35] rounded-xl text-sm text-gray-300 hover:border-gray-600 transition-all"
        >
          <RotateCcw className="w-4 h-4" />
          Reset to Current
        </button>
        {activePreset && (
          <span className="text-xs text-orange-400 font-medium">
            Preset: {activePreset} (click Apply Changes to save)
          </span>
        )}
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2.5 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-yellow-500 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-yellow-400">Configuration Notice</div>
            <p className="text-xs text-gray-400 mt-1">
              Risk parameters apply immediately to new trades. Exchange and agent config
              changes require an engine restart to take full effect. API keys are encrypted
              at rest and never exposed in full to the frontend.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
