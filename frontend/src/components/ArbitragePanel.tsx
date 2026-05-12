import { useArbLive, useArbStats, useArbControl, useArbOpportunities } from '@/hooks/useApi'
import { formatCurrency } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { ArrowRightLeft, Activity, Play, Square, Truck, Wallet, Clock, ChevronDown, ChevronUp, Calendar } from 'lucide-react'
import Tooltip from '@/components/Tooltip'
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

const PERIODS = [
  { key: 7, label: '7 Days' },
  { key: 30, label: '30 Days' },
  { key: 180, label: '6 Months' },
  { key: 0, label: 'All' },
] as const

export default function ArbitragePanel() {
  const { data: live } = useArbLive()
  const { data: stats } = useArbStats()
  const arb = useArbControl()
  const queryClient = useQueryClient()
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [periodDays, setPeriodDays] = useState<number>(0)
  const [showHistory, setShowHistory] = useState(false)

  const { data: histData } = useArbOpportunities(200, periodDays)
  const historical = histData?.opportunities || []

  const opps = live?.opportunities || []
  const isRunning = stats?.is_running ?? false

  const handleToggle = async () => {
    if (isRunning) {
      await arb.stop.mutateAsync()
    } else {
      await arb.start.mutateAsync()
    }
    queryClient.invalidateQueries({ queryKey: ['arb_stats'] })
    queryClient.invalidateQueries({ queryKey: ['arb_live'] })
  }

  const periodStats = () => {
    const executed = historical.filter((o) => o.executed)
    const totalProfit = executed.reduce((sum, o) => sum + (o.net_profit_usdt || 0), 0)
    return {
      count: executed.length,
      profit: totalProfit,
    }
  }

  const pStats = periodStats()

  return (
    <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ArrowRightLeft className="w-5 h-5 text-blue-400" />
          <span className="text-sm font-semibold text-gray-200">Arbitrage Scanner</span>
        </div>
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium ${
            isRunning ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gray-500/10 text-gray-400'
          }`}>
            <Activity className="w-3 h-3" />
            {isRunning ? 'Scanning' : 'Stopped'}
          </div>
          <button
            onClick={handleToggle}
            disabled={arb.start.isPending || arb.stop.isPending}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50',
              isRunning
                ? 'bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20'
                : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20'
            )}
          >
            {isRunning ? <Square className="w-3 h-3" /> : <Play className="w-3 h-3" />}
            {arb.start.isPending || arb.stop.isPending
              ? '...'
              : isRunning
                ? 'Stop'
                : 'Start Scan'}
          </button>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          <div className="bg-[#0a0a0f] rounded-lg p-2.5">
            <Tooltip content="Number of market scans performed by the arbitrage engine">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 cursor-help">Scans</div>
            </Tooltip>
            <div className="text-base font-bold text-white">{stats.scans || 0}</div>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-2.5">
            <Tooltip content="Total arbitrage opportunities detected across all exchanges">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 cursor-help">Found</div>
            </Tooltip>
            <div className="text-base font-bold text-white">{stats.opportunities_found || 0}</div>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-2.5">
            <Tooltip content="Opportunities that passed filters and were actually traded">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 cursor-help">Executed</div>
            </Tooltip>
            <div className="text-base font-bold text-white">{stats.executed || 0}</div>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-2.5">
            <Tooltip content="Net profit from all executed arbitrage trades after fees">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1 cursor-help">Profit</div>
            </Tooltip>
            <div className={cn(
              'text-base font-bold',
              (stats.total_profit_usdt || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
            )}>
              {formatCurrency(stats.total_profit_usdt || 0)}
            </div>
          </div>
        </div>
      )}

      {/* Live Opportunities */}
      <div className="mb-4">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Live Opportunities</div>
        {opps.length === 0 ? (
          <div className="text-center py-4 text-gray-500 text-sm bg-[#0a0a0f] rounded-lg">
            {isRunning ? 'Scanning markets...' : 'Scanner stopped. Click Start Scan to begin.'}
          </div>
        ) : (
          <div className="space-y-2">
            {opps.slice(0, 5).map((opp, i) => renderOpp(opp, i, expandedIdx, setExpandedIdx))}
          </div>
        )}
      </div>

      {/* Historical Toggle */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="flex items-center gap-2 text-sm font-semibold text-gray-200 hover:text-white transition-colors"
        >
          <Calendar className="w-4 h-4 text-blue-400" />
          Historical Trades
          {showHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {showHistory && (
          <div className="flex items-center gap-1">
            {PERIODS.map((p) => (
              <button
                key={p.key}
                onClick={() => setPeriodDays(p.key)}
                className={cn(
                  'px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all',
                  periodDays === p.key
                    ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                    : 'bg-[#0a0a0f] text-gray-500 border border-[#2a2a35] hover:text-gray-300'
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Historical List */}
      {showHistory && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-gray-500 px-1">
            <span>{historical.length} opportunities · {pStats.count} executed</span>
            <span className={pStats.profit >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {pStats.profit >= 0 ? '+' : ''}{formatCurrency(pStats.profit)}
            </span>
          </div>
          {historical.length === 0 ? (
            <div className="text-center py-6 text-gray-500 text-sm bg-[#0a0a0f] rounded-lg">
              No historical trades for this period
            </div>
          ) : (
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {historical.map((opp, i) => renderOpp(opp, i + 1000, expandedIdx, setExpandedIdx))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function renderOpp(
  opp: import('@/types').ArbOpportunity,
  i: number,
  expandedIdx: number | null,
  setExpandedIdx: (idx: number | null) => void
) {
  const isOpen = expandedIdx === i
  const priceDiff = opp.sell_price - opp.buy_price
  const grossProfit = opp.size_usdt * (opp.spread_pct / 100)
  const feeCost = opp.size_usdt * (opp.fees_pct / 100)
  const netProfit = opp.net_profit_usdt
  return (
    <div key={i}>
      <div
        className="flex items-center justify-between bg-[#0a0a0f] rounded-lg px-3 py-2 text-xs cursor-pointer hover:bg-[#0f0f18] transition-colors"
        onClick={() => setExpandedIdx(isOpen ? null : i)}
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-400">{opp.symbol}</span>
          <span className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-bold uppercase',
            opp.strategy === 'cross_exchange'
              ? 'bg-blue-500/15 text-blue-400'
              : opp.strategy === 'spot_perp'
                ? 'bg-purple-500/15 text-purple-400'
                : 'bg-orange-500/15 text-orange-400'
          )}>
            {opp.strategy === 'cross_exchange'
              ? 'Cross'
              : opp.strategy === 'spot_perp'
                ? 'Basis'
                : 'Transfer'}
          </span>
          {opp.executed && (
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 text-[10px] font-bold">
              FILLED
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-gray-500">
            {opp.buy_exchange} <span className="text-gray-300">{opp.buy_price.toFixed(2)}</span>
          </span>
          <ArrowRightLeft className="w-3 h-3 text-gray-600" />
          <span className="text-gray-500">
            {opp.sell_exchange} <span className="text-gray-300">{opp.sell_price.toFixed(2)}</span>
          </span>
          <span className={cn(
            'font-bold',
            opp.net_profit_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
          )}>
            +{opp.net_profit_pct.toFixed(3)}%
          </span>
          {isOpen ? (
            <ChevronUp className="w-3.5 h-3.5 text-gray-500" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-gray-500" />
          )}
        </div>
      </div>

      {isOpen && (
        <div className="bg-[#0d0d14] rounded-b-lg px-4 py-4 space-y-3 text-xs border-t border-[#1f1f2e]">
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-[#16161f] rounded-lg p-3">
              <div className="text-[10px] text-gray-500 uppercase mb-1">Buy on {opp.buy_exchange}</div>
              <div className="text-sm font-bold text-white">{opp.buy_price.toFixed(2)}</div>
            </div>
            <div className="bg-[#16161f] rounded-lg p-3">
              <div className="text-[10px] text-gray-500 uppercase mb-1">Sell on {opp.sell_exchange}</div>
              <div className="text-sm font-bold text-white">{opp.sell_price.toFixed(2)}</div>
            </div>
            <div className="bg-[#16161f] rounded-lg p-3">
              <div className="text-[10px] text-gray-500 uppercase mb-1">Price Difference</div>
              <div className="text-sm font-bold text-emerald-400">+{priceDiff.toFixed(2)}</div>
            </div>
          </div>

          <div className="bg-[#16161f] rounded-lg p-3 space-y-2">
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">Profit Breakdown</div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Trade Size</span>
                <span className="text-white font-mono">{formatCurrency(opp.size_usdt)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Gross Spread</span>
                <span className="text-emerald-400 font-mono">+{opp.spread_pct.toFixed(3)}% = {formatCurrency(grossProfit)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Fees & Costs</span>
                <span className="text-red-400 font-mono">-{opp.fees_pct.toFixed(3)}% = {formatCurrency(feeCost)}</span>
              </div>
              <div className="border-t border-[#2a2a35] pt-1.5 flex items-center justify-between">
                <span className="text-gray-300 font-semibold">Net Profit</span>
                <span className="text-emerald-400 font-bold font-mono">+{formatCurrency(netProfit)}</span>
              </div>
            </div>
          </div>

          {opp.strategy === 'transfer_arb' && (
            <div className="grid grid-cols-2 gap-2">
              <div className="flex items-center gap-1.5 text-gray-400">
                <Truck className="w-3 h-3 text-orange-400" />
                Withdraw: <span className="text-white">{opp.withdrawal_fee?.toFixed(8) ?? '—'} {opp.symbol.split('/')[0]}</span>
              </div>
              <div className="flex items-center gap-1.5 text-gray-400">
                <Wallet className="w-3 h-3 text-blue-400" />
                Deposit: <span className="text-white">{opp.deposit_fee?.toFixed(8) ?? '—'} {opp.symbol.split('/')[0]}</span>
              </div>
              <div className="flex items-center gap-1.5 text-gray-400">
                <Clock className="w-3 h-3 text-emerald-400" />
                Transfer: <span className="text-white">~{opp.withdrawal_time_min ?? '—'} min</span>
              </div>
              <div className="flex items-center gap-1.5 text-gray-400">
                <Activity className="w-3 h-3 text-purple-400" />
                Network: <span className="text-white">{opp.network_fee_usdt?.toFixed(4) ?? '—'} USDT</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
