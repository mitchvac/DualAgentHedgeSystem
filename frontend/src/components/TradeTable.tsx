import { useState } from 'react'
import { formatCurrency, formatPercentage, getStatusBg } from '@/lib/utils'
import type { Trade } from '@/types'
import { ArrowUpRight, ArrowDownRight, ChevronDown, ChevronUp } from 'lucide-react'
import TradeDetailModal from './TradeDetailModal'
import Tooltip from './Tooltip'

interface TradeTableProps {
  trades: Trade[]
}

export default function TradeTable({ trades }: TradeTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null)

  if (!trades.length) {
    return (
      <div className="text-center py-12 text-gray-500 text-sm">
        No trades recorded yet
      </div>
    )
  }

  const toggleRow = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-[#1f1f2e]">
            <th className="text-left py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Unique trade package ID and the long/short exchange pair">Package</Tooltip>
            </th>
            <th className="text-left py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Trading pair symbol (e.g. BTC-USDT)">Symbol</Tooltip>
            </th>
            <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Quantity of the long leg position">Long Qty</Tooltip>
            </th>
            <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Entry price of the short leg position">Short @</Tooltip>
            </th>
            <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Total funding fees paid while holding this position">Funding</Tooltip>
            </th>
            <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Capital allocated to this trade package at entry">Risked</Tooltip>
            </th>
            <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Realized profit or loss in USDT">PnL</Tooltip>
            </th>
            <th className="text-right py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Return as a percentage of risked capital">PnL %</Tooltip>
            </th>
            <th className="text-left py-3 px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider">
              <Tooltip content="Current state: open, closed, or killed">Status</Tooltip>
            </th>
            <th className="py-3 px-2 w-8"></th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => {
            const isOpen = expanded.has(trade.package_id)
            return (
              <>
                <tr
                  key={trade.package_id}
                  className="border-b border-[#1f1f2e]/50 hover:bg-white/[0.02] transition-colors cursor-pointer"
                  onClick={() => setSelectedTrade(trade)}
                >
                  <td className="py-3 px-3">
                    <code className="bg-[#1a1a24] px-2 py-1 rounded text-xs text-gray-300 font-mono">
                      {trade.package_id}
                    </code>
                    <div className="text-[10px] text-gray-500 mt-0.5">{trade.long_exchange} / {trade.short_exchange}</div>
                  </td>
                  <td className="py-3 px-3 text-sm text-gray-200">{trade.symbol}</td>
                  <td className="py-3 px-3 text-right text-xs text-gray-300 font-mono">
                    {trade.long_qty?.toFixed(4) ?? '—'}
                  </td>
                  <td className="py-3 px-3 text-right text-xs text-gray-300 font-mono">
                    {trade.short_entry?.toFixed(1) ?? '—'}
                  </td>
                  <td className="py-3 px-3 text-right text-xs font-mono">
                    {(trade.funding_paid || 0) > 0 ? (
                      <span className="text-red-400">-{formatCurrency(trade.funding_paid || 0)}</span>
                    ) : (
                      <span className="text-gray-500">—</span>
                    )}
                  </td>
                  <td className="py-3 px-3 text-right text-sm text-gray-300">
                    {formatCurrency(trade.risk_budget)}
                  </td>
                  <td className={`py-3 px-3 text-right text-sm font-medium ${trade.pnl_usdt >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {formatCurrency(trade.pnl_usdt)}
                  </td>
                  <td className={`py-3 px-3 text-right text-sm font-medium ${trade.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {formatPercentage(trade.pnl_pct)}
                  </td>
                  <td className="py-3 px-3">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-semibold uppercase ${getStatusBg(trade.status)}`}>
                      {trade.status}
                    </span>
                  </td>
                  <td className="py-3 px-2" onClick={(e) => { e.stopPropagation(); toggleRow(trade.package_id) }}>
                    {isOpen ? (
                      <ChevronUp className="w-4 h-4 text-gray-500" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-gray-500" />
                    )}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-[#0a0a0f]/50">
                    <td colSpan={9} className="py-4 px-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Long Leg Detail */}
                        <div className="bg-[#16161f] rounded-xl border border-[#2a2a35] p-4 space-y-3">
                          <div className="flex items-center gap-2">
                            <ArrowUpRight className="w-4 h-4 text-emerald-400" />
                            <span className="text-sm font-semibold text-emerald-400">Long Leg</span>
                            <span className="text-xs text-gray-500 ml-2">{trade.long_exchange}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-3 text-xs">
                            <div>
                              <div className="text-gray-500">Quantity</div>
                              <div className="text-gray-200 font-mono">{trade.long_qty?.toFixed(6) ?? '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Notional</div>
                              <div className="text-gray-200 font-mono">{trade.long_notional ? `$${trade.long_notional.toFixed(2)}` : '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Entry Price</div>
                              <div className="text-gray-200 font-mono">{trade.long_entry?.toFixed(2) ?? '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Leverage</div>
                              <div className="text-orange-400 font-mono">{trade.long_leverage ? `${trade.long_leverage}x` : '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">PnL</div>
                              <div className={`font-mono ${(trade.long_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {trade.long_pnl ? `${trade.long_pnl >= 0 ? '+' : ''}${trade.long_pnl.toFixed(2)}` : '—'}
                              </div>
                            </div>
                          </div>
                        </div>
                        {/* Short Leg Detail */}
                        <div className="bg-[#16161f] rounded-xl border border-[#2a2a35] p-4 space-y-3">
                          <div className="flex items-center gap-2">
                            <ArrowDownRight className="w-4 h-4 text-red-400" />
                            <span className="text-sm font-semibold text-red-400">Short Leg</span>
                            <span className="text-xs text-gray-500 ml-2">{trade.short_exchange}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-3 text-xs">
                            <div>
                              <div className="text-gray-500">Quantity</div>
                              <div className="text-gray-200 font-mono">{trade.short_qty?.toFixed(6) ?? '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Notional</div>
                              <div className="text-gray-200 font-mono">{trade.short_notional ? `$${trade.short_notional.toFixed(2)}` : '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Entry Price</div>
                              <div className="text-gray-200 font-mono">{trade.short_entry?.toFixed(2) ?? '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Leverage</div>
                              <div className="text-orange-400 font-mono">{trade.short_leverage ? `${trade.short_leverage}x` : '—'}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">PnL</div>
                              <div className={`font-mono ${(trade.short_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {trade.short_pnl ? `${trade.short_pnl >= 0 ? '+' : ''}${trade.short_pnl.toFixed(2)}` : '—'}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                      {trade.funding_paid !== undefined && trade.funding_paid !== 0 && (
                        <div className="mt-3 text-xs text-gray-500">
                          Funding costs: <span className="text-red-400">-${trade.funding_paid.toFixed(4)}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </>
            )
          })}
        </tbody>
      </table>
      <TradeDetailModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </div>
  )
}
