import { ArrowUp, ArrowDown } from 'lucide-react'
import type { ExchangeTrade } from '@/types'

interface RecentTradesProps {
  trades: ExchangeTrade[]
  title?: string
}

export default function RecentTrades({ trades, title = 'Recent Trades' }: RecentTradesProps) {
  return (
    <div className="space-y-2">
      <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{title}</h4>
      <div className="space-y-1 max-h-[180px] overflow-y-auto pr-1 scrollbar-thin">
        {trades.length === 0 ? (
          <div className="text-xs text-gray-600 py-2">No recent trades</div>
        ) : (
          trades.slice(0, 15).map((t, i) => (
            <div key={i} className="flex items-center justify-between text-xs py-0.5">
              <div className="flex items-center gap-1.5">
                {t.side === 'buy' ? (
                  <ArrowUp className="w-3 h-3 text-emerald-400" />
                ) : (
                  <ArrowDown className="w-3 h-3 text-red-400" />
                )}
                <span className={t.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}>
                  {t.side === 'buy' ? 'Buy' : 'Sell'}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-gray-300 font-mono">{t.price.toFixed(2)}</span>
                <span className="text-gray-500 font-mono">{t.amount.toFixed(4)}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
