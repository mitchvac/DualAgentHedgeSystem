import { X, ArrowUpRight, ArrowDownRight, Clock, Target, TrendingUp, Brain } from 'lucide-react'
import type { Trade } from '@/types'
import { formatCurrency, formatDate } from '@/lib/utils'

interface TradeDetailModalProps {
  trade: Trade | null
  onClose: () => void
}

export default function TradeDetailModal({ trade, onClose }: TradeDetailModalProps) {
  if (!trade) return null

  const duration = trade.closed_at
    ? Math.round((new Date(trade.closed_at).getTime() - new Date(trade.created_at).getTime()) / 60000)
    : trade.status === 'closed'
    ? Math.round((Date.now() - new Date(trade.created_at).getTime()) / 60000)
    : Math.round((Date.now() - new Date(trade.created_at).getTime()) / 60000)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] w-full max-w-lg p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">{trade.symbol}</h3>
            <p className="text-xs text-gray-500">{trade.package_id}</p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* PnL Header */}
        <div className="bg-[#0a0a0f] rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-gray-500">Total PnL</div>
            <div className={`text-2xl font-bold ${trade.pnl_usdt >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {trade.pnl_usdt >= 0 ? '+' : ''}{formatCurrency(trade.pnl_usdt)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-500">Return</div>
            <div className={`text-lg font-bold ${trade.pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {trade.pnl_pct >= 0 ? '+' : ''}{trade.pnl_pct.toFixed(2)}%
            </div>
          </div>
        </div>

        {/* Legs Detail */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-[#0a0a0f] rounded-xl p-3 space-y-2">
            <div className="flex items-center gap-2">
              <ArrowUpRight className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-semibold text-emerald-400">Long Leg</span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between"><span className="text-gray-500">Exchange</span><span className="text-gray-300">{trade.long_exchange}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Qty</span><span className="text-gray-300">{trade.long_qty?.toFixed(4) ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Entry</span><span className="text-gray-300">{trade.long_entry?.toFixed(2) ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Leverage</span><span className="text-orange-400">{trade.long_leverage ? `${trade.long_leverage}x` : '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">PnL</span><span className={trade.long_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{formatCurrency(trade.long_pnl)}</span></div>
            </div>
          </div>
          <div className="bg-[#0a0a0f] rounded-xl p-3 space-y-2">
            <div className="flex items-center gap-2">
              <ArrowDownRight className="w-4 h-4 text-red-400" />
              <span className="text-sm font-semibold text-red-400">Short Leg</span>
            </div>
            <div className="space-y-1 text-xs">
              <div className="flex justify-between"><span className="text-gray-500">Exchange</span><span className="text-gray-300">{trade.short_exchange}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Qty</span><span className="text-gray-300">{trade.short_qty?.toFixed(4) ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Entry</span><span className="text-gray-300">{trade.short_entry?.toFixed(2) ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">Leverage</span><span className="text-orange-400">{trade.short_leverage ? `${trade.short_leverage}x` : '—'}</span></div>
              <div className="flex justify-between"><span className="text-gray-500">PnL</span><span className={trade.short_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>{formatCurrency(trade.short_pnl)}</span></div>
            </div>
          </div>
        </div>

        {/* Meta */}
        <div className="bg-[#0a0a0f] rounded-xl p-3 space-y-2">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Trade Info</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center gap-2">
              <Clock className="w-3 h-3 text-gray-500" />
              <span className="text-gray-500">Duration:</span>
              <span className="text-gray-300">{duration} min</span>
            </div>
            <div className="flex items-center gap-2">
              <Target className="w-3 h-3 text-gray-500" />
              <span className="text-gray-500">Risked:</span>
              <span className="text-gray-300">{formatCurrency(trade.risk_budget)}</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp className="w-3 h-3 text-gray-500" />
              <span className="text-gray-500">Status:</span>
              <span className="text-gray-300 capitalize">{trade.status}</span>
            </div>
            {trade.funding_paid ? (
              <div className="flex items-center gap-2">
                <Brain className="w-3 h-3 text-gray-500" />
                <span className="text-gray-500">Funding:</span>
                <span className="text-red-400">-{formatCurrency(trade.funding_paid)}</span>
              </div>
            ) : null}
          </div>
          <div className="text-[10px] text-gray-600">
            Opened: {formatDate(trade.created_at)}
          </div>
        </div>
      </div>
    </div>
  )
}
