import { usePositions, useEquity } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { formatCurrency, cn } from '@/lib/utils'
import { ArrowUpRight, ArrowDownRight, Wallet } from 'lucide-react'

export default function PositionsPanel() {
  const { data } = usePositions()
  const { data: equityData } = useEquity()
  const { positions: wsPositions, equity: wsEquity } = useWebSocket()

  const positions = wsPositions.length > 0 ? wsPositions : data?.positions || []
  const equity = wsEquity ?? equityData?.equity_usdt ?? null

  const longs = positions.filter((p) => p.side === 'long')
  const shorts = positions.filter((p) => p.side === 'short')
  const totalUnrealized = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0)

  return (
    <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Wallet className="w-5 h-5 text-orange-400" />
          <span className="text-sm font-semibold text-gray-200">Live Positions</span>
        </div>
        <div className="text-right">
          {equity !== null && (
            <div className="text-lg font-bold text-white">{formatCurrency(equity)}</div>
          )}
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Equity</div>
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="text-center py-6 text-gray-500 text-sm">No open positions</div>
      ) : (
        <div className="space-y-3">
          {positions.map((pos) => {
            const isLong = pos.side === 'long'
            const pnlPositive = pos.unrealized_pnl >= 0
            return (
              <div
                key={`${pos.package_id}-${pos.side}`}
                className="bg-[#0a0a0f] rounded-xl p-3 border border-[#1f1f2e]"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-gray-300">{pos.symbol}</span>
                    <span
                      className={cn(
                        'px-1.5 py-0.5 rounded text-[10px] font-bold uppercase',
                        isLong ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
                      )}
                    >
                      {isLong ? 'LONG' : 'SHORT'}
                    </span>
                    <span className="text-[10px] text-gray-500">{pos.exchange}</span>
                  </div>
                  <div
                    className={cn(
                      'flex items-center gap-1 text-xs font-bold',
                      pnlPositive ? 'text-emerald-400' : 'text-red-400'
                    )}
                  >
                    {pnlPositive ? (
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    ) : (
                      <ArrowDownRight className="w-3.5 h-3.5" />
                    )}
                    {formatCurrency(pos.unrealized_pnl)}
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-2 text-xs">
                  <div>
                    <div className="text-gray-500 text-[10px]">Entry</div>
                    <div className="text-gray-200 font-medium">{pos.entry_price.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-[10px]">Mark</div>
                    <div className="text-gray-200 font-medium">{pos.current_price.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-[10px]">Size</div>
                    <div className="text-gray-200 font-medium">{pos.quantity.toFixed(4)}</div>
                  </div>
                  <div>
                    <div className="text-gray-500 text-[10px]">Lev</div>
                    <div className="text-gray-200 font-medium">{pos.leverage}x</div>
                  </div>
                </div>
              </div>
            )
          })}

          <div className="flex items-center justify-between pt-2 border-t border-[#1f1f2e]">
            <div className="text-xs text-gray-500">
              {longs.length} long · {shorts.length} short
            </div>
            <div
              className={cn(
                'text-sm font-bold',
                totalUnrealized >= 0 ? 'text-emerald-400' : 'text-red-400'
              )}
            >
              Unrealized: {formatCurrency(totalUnrealized)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
