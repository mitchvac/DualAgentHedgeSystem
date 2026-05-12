import type { ExchangeDepth } from '@/types'

interface ExchangeDepthPanelProps {
  depth: ExchangeDepth | null
  side: 'bids' | 'asks'
  title: string
  color: 'green' | 'red'
}

export default function ExchangeDepthPanel({ depth, side, title, color }: ExchangeDepthPanelProps) {
  const entries = depth?.[side] || []
  const maxAmount = entries.length > 0 ? Math.max(...entries.map(([, a]) => a)) : 1

  return (
    <div className="space-y-2">
      <h4 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{title}</h4>
      <div className="space-y-0.5">
        {entries.length === 0 ? (
          <div className="text-xs text-gray-600 py-2">No data</div>
        ) : (
          entries.map(([price, amount], i) => {
            const pct = (amount / maxAmount) * 100
            return (
              <div key={i} className="relative flex items-center justify-between text-xs py-0.5 px-1 rounded">
                {/* Background bar */}
                <div
                  className={`absolute inset-0 rounded ${color === 'green' ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}
                  style={{ width: `${pct}%` }}
                />
                <span className={`relative z-10 font-mono ${color === 'green' ? 'text-emerald-400' : 'text-red-400'}`}>
                  {price.toFixed(2)}
                </span>
                <span className="relative z-10 text-gray-400 font-mono">{amount.toFixed(4)}</span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
