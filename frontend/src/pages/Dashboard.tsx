import { useMemo } from 'react'
import { DollarSign, Percent, Activity, Package, Cpu, Users, Shield, AlertTriangle } from 'lucide-react'
import KPICard from '@/components/KPICard'
import PnLChart from '@/components/PnLChart'
import AgentSwarmChart from '@/components/AgentSwarmChart'
import TradeTable from '@/components/TradeTable'
import ArbitragePanel from '@/components/ArbitragePanel'
import DefensePanel from '@/components/DefensePanel'
import PositionsPanel from '@/components/PositionsPanel'
import WatchlistPrices from '@/components/WatchlistPrices'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAnalytics, useSystemStatus, useHealth, useSwarmConsensus, useRisk } from '@/hooks/useApi'
import { formatCurrency } from '@/lib/utils'
import Tooltip from '@/components/Tooltip'

export default function Dashboard() {
  const { trades, defense, positions, consensus: wsConsensus } = useWebSocket()
  const { data: analytics } = useAnalytics()
  const { data: status } = useSystemStatus()
  const { data: health } = useHealth()
  const { data: consensusData } = useSwarmConsensus()
  const { data: risk } = useRisk()

  const consensus = wsConsensus || consensusData || null

  const chartData = useMemo(() => {
    const closed = trades
      .filter((t) => t.status === 'closed')
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())

    let cum = 0
    return closed.map((t) => {
      cum += t.pnl_usdt
      return {
        date: new Date(t.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        pnl: cum,
      }
    })
  }, [trades])

  const totalPnl = trades.reduce((sum, t) => sum + t.pnl_usdt, 0)
  const winCount = trades.filter((t) => t.pnl_usdt > 0).length
  const closedCount = trades.filter((t) => t.status === 'closed').length
  const winRate = closedCount > 0 ? (winCount / closedCount) * 100 : 0

  const isEngineRunning = health?.engine_running ?? false

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Dashboard Overview</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Real-time monitoring of your dual-agent hedge system
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border ${
            isEngineRunning
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
              : 'bg-red-500/10 text-red-400 border-red-500/20'
          }`}>
            <Cpu className="w-3.5 h-3.5" />
            Engine {isEngineRunning ? 'Running' : 'Stopped'}
          </div>
          <span className={`text-xs font-bold px-2.5 py-1.5 rounded-lg border ${
            status?.paper_trading ? 'bg-green-500/15 text-green-400 border-green-500/30' : 'bg-red-500/15 text-red-400 border-red-500/30'
          }`}>
            {status?.paper_trading ? 'PAPER' : 'LIVE'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Total Realized PnL"
          value={formatCurrency(totalPnl)}
          delta={totalPnl}
          icon={<DollarSign className="w-5 h-5 text-blue-400" />}
          color="blue"
          tooltip="Sum of all closed trade profits and losses in USDT"
        />
        <KPICard
          title="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          delta={winRate - 50}
          icon={<Percent className="w-5 h-5 text-purple-400" />}
          color="purple"
          tooltip="Percentage of closed trades that were profitable"
        />
        <KPICard
          title="Closed Trades"
          value={closedCount}
          icon={<Activity className="w-5 h-5 text-emerald-400" />}
          color="green"
          tooltip="Total number of trade packages that have been fully closed"
        />
        <KPICard
          title="Active Legs"
          value={positions.length}
          icon={<Package className="w-5 h-5 text-orange-400" />}
          color="orange"
          tooltip="Number of open position legs currently held across exchanges"
        />
      </div>

      {/* Risk Dashboard */}
      {risk && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-blue-400" />
              <Tooltip content="Total notional value of open positions as a percentage of equity">
                <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Exposure</span>
              </Tooltip>
            </div>
            <div className="text-xl font-bold text-white">{risk.exposure_pct.toFixed(1)}%</div>
            <div className="text-xs text-gray-500">{formatCurrency(risk.total_exposure)} notional</div>
          </div>
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <Tooltip content="Peak-to-trough equity decline today vs your max daily drawdown limit">
                <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Daily DD</span>
              </Tooltip>
            </div>
            <div className={`text-xl font-bold ${risk.daily_drawdown_pct >= risk.max_drawdown_limit * 0.8 ? 'text-red-400' : 'text-orange-400'}`}>
              {risk.daily_drawdown_pct.toFixed(2)}%
            </div>
            <div className="text-xs text-gray-500">Limit: {risk.max_drawdown_limit}%</div>
          </div>
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Package className="w-4 h-4 text-emerald-400" />
              <Tooltip content="Number of individual open position legs across all exchanges">
                <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Positions</span>
              </Tooltip>
            </div>
            <div className="text-xl font-bold text-white">{risk.open_positions}</div>
            <div className="text-xs text-gray-500">{risk.active_packages} packages active</div>
          </div>
          <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-4 h-4 text-purple-400" />
              <Tooltip content="Whether trading is currently halted due to risk limits being breached">
                <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Status</span>
              </Tooltip>
            </div>
            <div className={`text-xl font-bold ${risk.daily_halted ? 'text-red-400' : 'text-emerald-400'}`}>
              {risk.daily_halted ? 'HALTED' : 'OK'}
            </div>
            <div className="text-xs text-gray-500">{risk.daily_halted ? 'Drawdown limit hit' : 'Within limits'}</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-200">Cumulative PnL</h3>
            {analytics && (
              <div className="flex items-center gap-4 text-xs">
                <span className="text-gray-400">
                  PF: <span className="text-white font-medium">{analytics.profit_factor.toFixed(2)}</span>
                </span>
                <span className="text-gray-400">
                  Avg Win: <span className="text-emerald-400 font-medium">{formatCurrency(analytics.avg_win)}</span>
                </span>
                <span className="text-gray-400">
                  Avg Loss: <span className="text-red-400 font-medium">{formatCurrency(analytics.avg_loss)}</span>
                </span>
              </div>
            )}
          </div>
          <PnLChart data={chartData} />
        </div>

        <PositionsPanel />
      </div>

      <ArbitragePanel />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-200">Recent Trade Packages</h3>
            <span className="text-xs text-gray-500">Last 10 trades</span>
          </div>
          <TradeTable trades={trades.slice(0, 10)} />
        </div>

        <DefensePanel defense={defense} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Watchlist</h3>
          <WatchlistPrices symbols={status?.watchlist || []} />
        </div>

        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
          <div className="flex items-center gap-2 mb-4">
            <Users className="w-4 h-4 text-orange-400" />
            <h3 className="text-sm font-semibold text-gray-200">Agent Swarm Overview</h3>
          </div>
          <AgentSwarmChart consensus={consensus} />
        </div>
      </div>
    </div>
  )
}
