import { usePortfolio } from '@/hooks/useApi'
import { formatCurrency, cn } from '@/lib/utils'
import { TrendingUp, TrendingDown, Wallet, Activity } from 'lucide-react'
import Tooltip from '@/components/Tooltip'
import { useState } from 'react'

const PERIODS = [
  { key: 7, label: '7D' },
  { key: 30, label: '30D' },
  { key: 90, label: '90D' },
]

export default function Portfolio() {
  const [days, setDays] = useState(30)
  const { data } = usePortfolio(days)

  const equityCurve = data?.equity_curve || []
  const monthly = data?.monthly_returns || []
  const maxDd = data?.max_drawdown || 0

  const maxEquity = equityCurve.length > 0 ? Math.max(...equityCurve.map((e) => e.equity)) : 0
  const minEquity = equityCurve.length > 0 ? Math.min(...equityCurve.map((e) => e.equity)) : 0
  const range = maxEquity - minEquity || 1

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Portfolio</h2>
          <p className="text-sm text-gray-500 mt-0.5">Equity curve and performance over time</p>
        </div>
        <div className="flex items-center gap-1">
          {PERIODS.map((p) => (
            <button
              key={p.key}
              onClick={() => setDays(p.key)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                days === p.key
                  ? 'bg-blue-500/15 text-blue-400 border border-blue-500/30'
                  : 'bg-[#16161f] text-gray-500 border border-[#2a2a35] hover:text-gray-300'
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Wallet className="w-4 h-4 text-blue-400" />
            <Tooltip content="Your total account value including unrealized PnL">
              <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Current Equity</span>
            </Tooltip>
          </div>
          <div className="text-xl font-bold text-white">{formatCurrency(data?.current_equity || 0)}</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-red-400" />
            <Tooltip content="Largest peak-to-trough decline in equity over the selected period">
              <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Max Drawdown</span>
            </Tooltip>
          </div>
          <div className="text-xl font-bold text-red-400">{maxDd.toFixed(2)}%</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <Tooltip content="Highest equity value reached during the selected period">
              <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Peak Equity</span>
            </Tooltip>
          </div>
          <div className="text-xl font-bold text-white">{formatCurrency(maxEquity)}</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="w-4 h-4 text-orange-400" />
            <Tooltip content="Lowest equity value reached during the selected period">
              <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Low Equity</span>
            </Tooltip>
          </div>
          <div className="text-xl font-bold text-white">{formatCurrency(minEquity)}</div>
        </div>
      </div>

      {/* Equity Chart */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
        <h3 className="text-sm font-semibold text-gray-200 mb-4">Equity Curve</h3>
        {equityCurve.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">No equity data yet. Data builds over time.</div>
        ) : (
          <div className="h-64 flex items-end gap-1">
            {equityCurve.map((pt, i) => {
              const h = ((pt.equity - minEquity) / range) * 100
              return (
                <div key={i} className="flex-1 flex flex-col justify-end group relative">
                  <div
                    className={cn(
                      'w-full rounded-sm transition-all',
                      pt.drawdown > 5 ? 'bg-red-500/60' : pt.drawdown > 2 ? 'bg-orange-500/60' : 'bg-emerald-500/60'
                    )}
                    style={{ height: `${Math.max(h, 5)}%` }}
                  />
                  <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 bg-[#0a0a0f] border border-[#2a2a35] px-2 py-1 rounded text-[10px] text-gray-300 opacity-0 group-hover:opacity-100 whitespace-nowrap z-10">
                    {formatCurrency(pt.equity)} · DD {pt.drawdown.toFixed(2)}%
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Monthly Returns */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
        <h3 className="text-sm font-semibold text-gray-200 mb-4">Monthly Returns</h3>
        {monthly.length === 0 ? (
          <div className="text-center py-12 text-gray-500 text-sm">No closed trades yet</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {monthly.map((m) => (
              <div key={m.month} className="bg-[#0a0a0f] rounded-xl p-3 text-center">
                <div className="text-[10px] text-gray-500 uppercase mb-1">{m.month}</div>
                <div className={cn('text-sm font-bold', m.pnl >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                  {m.pnl >= 0 ? '+' : ''}{formatCurrency(m.pnl)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
