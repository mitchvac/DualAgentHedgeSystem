import { Briefcase, ArrowUpRight } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import { cn } from '@/lib/utils'
import type { ExchangePosition } from '@/types'

interface LivePositionsProps {
  longPositions: ExchangePosition[]
  shortPositions: ExchangePosition[]
  equity?: number
  longExchange?: string
  shortExchange?: string
}

export default function LivePositions({
  longPositions,
  shortPositions,
  equity,
  longExchange = 'okx',
  shortExchange = 'bybit',
}: LivePositionsProps) {
  const allPositions = [
    ...longPositions.map(p => ({ ...p, panelExchange: longExchange, panelSide: 'long' as const })),
    ...shortPositions.map(p => ({ ...p, panelExchange: shortExchange, panelSide: 'short' as const })),
  ]

  const totalUnrealized = allPositions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0)
  const longCount = longPositions.length
  const shortCount = shortPositions.length

  return (
    <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-orange-400" />
          <h3 className="text-sm font-semibold text-gray-200">Live Positions</h3>
        </div>
        {equity !== undefined && (
          <div className="text-right">
            <div className="text-xl font-bold text-white">{formatCurrency(equity)}</div>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">Equity</div>
          </div>
        )}
      </div>

      {/* Position Cards */}
      <div className="space-y-3">
        {allPositions.length === 0 ? (
          <div className="text-center py-6 text-gray-500 text-sm">
            No open positions
          </div>
        ) : (
          allPositions.map((p, i) => (
            <div
              key={i}
              className="bg-[#0a0a0f] rounded-xl px-4 py-3 border border-[#1f1f2e]"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{p.symbol}</span>
                  <span className={cn(
                    'px-2 py-0.5 rounded text-[10px] font-bold uppercase',
                    p.panelSide === 'long'
                      ? 'bg-emerald-500/15 text-emerald-400'
                      : 'bg-red-500/15 text-red-400'
                  )}>
                    {p.panelSide === 'long' ? 'LONG' : 'SHORT'}
                  </span>
                  <span className="text-[10px] text-gray-500">{p.panelExchange}</span>
                </div>
                <div className={cn(
                  'flex items-center gap-1 text-sm font-bold',
                  (p.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                )}>
                  <ArrowUpRight className={cn(
                    'w-3.5 h-3.5',
                    (p.unrealized_pnl || 0) < 0 && 'rotate-90'
                  )} />
                  {formatCurrency(p.unrealized_pnl || 0)}
                </div>
              </div>

              <div className="grid grid-cols-4 gap-2 text-xs">
                <div>
                  <div className="text-gray-500 text-[10px]">Entry</div>
                  <div className="text-white font-mono">{p.entry_price.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-gray-500 text-[10px]">Mark</div>
                  <div className="text-white font-mono">{p.mark_price.toFixed(2)}</div>
                </div>
                <div>
                  <div className="text-gray-500 text-[10px]">Size</div>
                  <div className="text-white font-mono">{p.contracts.toFixed(4)}</div>
                </div>
                <div>
                  <div className="text-gray-500 text-[10px]">Lev</div>
                  <div className="text-white font-mono">{p.leverage}x</div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      {allPositions.length > 0 && (
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-[#2a2a35]">
          <span className="text-xs text-gray-500">
            {longCount} long · {shortCount} short
          </span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Unrealized:</span>
            <span className={cn(
              'text-sm font-bold',
              totalUnrealized >= 0 ? 'text-emerald-400' : 'text-red-400'
            )}>
              {formatCurrency(totalUnrealized)}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
