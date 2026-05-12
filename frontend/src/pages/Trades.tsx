import { Download, Filter, RefreshCw, Wallet, TrendingUp, TrendingDown, PiggyBank, GitCompare } from 'lucide-react'
import TradeTable from '@/components/TradeTable'
import PnLChart from '@/components/PnLChart'
import { useTrades, useEquity, useArbStats } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useMemo, useState } from 'react'
import { formatCurrency, cn } from '@/lib/utils'

export default function Trades() {
  const { data, refetch, isFetching } = useTrades(200)
  const { data: equityData } = useEquity()
  const { data: arbStats } = useArbStats()
  const { trades: wsTrades } = useWebSocket()
  const [filter, setFilter] = useState<'all' | 'active' | 'closed' | 'killed'>('all')

  const allTrades = wsTrades.length > 0 ? wsTrades : data?.trades || []

  const filtered = useMemo(() => {
    if (filter === 'all') return allTrades
    return allTrades.filter((t) => t.status === filter)
  }, [allTrades, filter])

  const chartData = useMemo(() => {
    const closed = allTrades
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
  }, [allTrades])

  const stats = useMemo(() => {
    const totalPnl = allTrades.reduce((sum, t) => sum + t.pnl_usdt, 0)
    const totalRisked = allTrades.reduce((sum, t) => sum + (t.risk_budget || 0), 0)
    const totalFunding = allTrades.reduce((sum, t) => sum + (t.funding_paid || 0), 0)
    const wins = allTrades.filter((t) => t.pnl_usdt > 0).length
    const losses = allTrades.filter((t) => t.pnl_usdt <= 0).length
    const activeTrades = allTrades.filter((t) => t.status === 'active').length
    const activeRisk = allTrades
      .filter((t) => t.status === 'active')
      .reduce((sum, t) => sum + (t.risk_budget || 0), 0)
    return { totalPnl, totalRisked, totalFunding, wins, losses, activeTrades, activeRisk }
  }, [allTrades])

  const handleExport = () => {
    const csv = [
      'Package ID,Symbol,Long Exchange,Short Exchange,Long Qty,Short Qty,Long Notional,Short Notional,Long Entry,Short Entry,Long Lev,Short Lev,Long PnL,Short PnL,Funding,Status,PnL USDT,PnL %,Risk Budget,Close Reason,Created At',
      ...filtered.map((t) =>
        [t.package_id, t.symbol, t.long_exchange, t.short_exchange, t.long_qty, t.short_qty, t.long_notional, t.short_notional, t.long_entry, t.short_entry, t.long_leverage, t.short_leverage, t.long_pnl, t.short_pnl, t.funding_paid, t.status, t.pnl_usdt, t.pnl_pct, t.risk_budget, t.close_reason || '', t.created_at].join(',')
      ),
    ].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `hedgeswarm_trades_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const filters: { key: typeof filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'active', label: 'Active' },
    { key: 'closed', label: 'Closed' },
    { key: 'killed', label: 'Killed' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Trade History</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {allTrades.length} total trades · {stats.wins}W / {stats.losses}L
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-4 py-2 bg-[#16161f] border border-[#2a2a35] rounded-xl text-sm text-gray-300 hover:border-orange-500/30 hover:text-white transition-all disabled:opacity-50"
          >
            <RefreshCw className={cn('w-4 h-4', isFetching && 'animate-spin')} />
            {isFetching ? 'Refreshing...' : 'Refresh'}
          </button>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 bg-[#16161f] border border-[#2a2a35] rounded-xl text-sm text-gray-300 hover:border-orange-500/30 hover:text-white transition-all"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        </div>
      </div>

      {/* Capital Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Wallet className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-gray-500 uppercase tracking-wider">Current Equity</span>
          </div>
          <div className="text-xl font-bold text-white">{formatCurrency(equityData?.equity_usdt || 0)}</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <PiggyBank className="w-4 h-4 text-orange-400" />
            <span className="text-xs text-gray-500 uppercase tracking-wider">Total Risked</span>
          </div>
          <div className="text-xl font-bold text-white">{formatCurrency(stats.totalRisked)}</div>
          {stats.activeTrades > 0 && (
            <div className="text-xs text-gray-500 mt-1">{stats.activeTrades} active · {formatCurrency(stats.activeRisk)} at risk</div>
          )}
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span className="text-xs text-gray-500 uppercase tracking-wider">Total PnL</span>
          </div>
          <div className={`text-xl font-bold ${stats.totalPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {stats.totalPnl >= 0 ? '+' : ''}{formatCurrency(stats.totalPnl)}
          </div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="w-4 h-4 text-red-400" />
            <span className="text-xs text-gray-500 uppercase tracking-wider">Funding Costs</span>
          </div>
          <div className="text-xl font-bold text-red-400">-{formatCurrency(stats.totalFunding)}</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <GitCompare className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-gray-500 uppercase tracking-wider">Arbitrage Profit</span>
          </div>
          <div className="text-xl font-bold text-purple-400">
            +{formatCurrency(arbStats?.total_profit_usdt || 0)}
          </div>
          {arbStats && arbStats.executed > 0 && (
            <div className="text-xs text-gray-500 mt-1">{arbStats.executed} trades executed</div>
          )}
        </div>
      </div>

      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
        <PnLChart data={chartData} height={280} />
      </div>

      <div className="flex items-center gap-2">
        <Filter className="w-4 h-4 text-gray-500" />
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              filter === f.key
                ? 'bg-orange-500/15 text-orange-400 border border-orange-500/30'
                : 'bg-[#16161f] text-gray-400 border border-[#2a2a35] hover:border-gray-600'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
        <TradeTable trades={filtered} />
      </div>
    </div>
  )
}
