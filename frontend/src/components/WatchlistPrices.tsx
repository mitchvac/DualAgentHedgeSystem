import { useMarketSnapshot } from '@/hooks/useApi'
import { formatCurrency, cn, formatPercentage } from '@/lib/utils'
import { TrendingUp, TrendingDown } from 'lucide-react'

function WatchlistCard({ symbol }: { symbol: string }) {
  const { data: snap, isLoading, isError } = useMarketSnapshot(symbol)

  if (isLoading) {
    return (
      <div className="bg-[#16161f] rounded-xl border border-[#2a2a35] p-4 animate-pulse">
        <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider mb-1">{symbol}</div>
        <div className="h-6 bg-[#2a2a35] rounded w-20" />
      </div>
    )
  }

  if (isError || !snap) {
    return (
      <div className="bg-[#16161f] rounded-xl border border-[#2a2a35] p-4">
        <div className="text-xs text-gray-500 font-semibold uppercase tracking-wider mb-1">{symbol}</div>
        <div className="text-sm text-red-400">Unavailable</div>
      </div>
    )
  }

  const isPositive = snap.change_24h_pct >= 0

  return (
    <div className="bg-[#16161f] rounded-xl border border-[#2a2a35] p-4 hover:border-orange-500/30 transition-colors">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">{symbol}</span>
        {isPositive ? (
          <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
        ) : (
          <TrendingDown className="w-3.5 h-3.5 text-red-400" />
        )}
      </div>
      <div className="text-lg font-bold text-white">{formatCurrency(snap.mark_price)}</div>
      <div className={cn('text-xs font-medium mt-0.5', isPositive ? 'text-emerald-400' : 'text-red-400')}>
        {formatPercentage(snap.change_24h_pct)} · Vol {(snap.volume_24h / 1e6).toFixed(1)}M
      </div>
      <div className="text-[10px] text-gray-600 mt-1">
        Funding: {(snap.funding_rate * 100).toFixed(4)}%
      </div>
    </div>
  )
}

interface WatchlistPricesProps {
  symbols: string[]
}

export default function WatchlistPrices({ symbols }: WatchlistPricesProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {symbols.map((sym) => (
        <WatchlistCard key={sym} symbol={sym} />
      ))}
    </div>
  )
}
