import { TrendingUp, TrendingDown, Minus, Zap, Activity } from 'lucide-react'
import type { SwarmConsensus } from '@/types'

interface SwarmSignalGaugeProps {
  consensus: SwarmConsensus | null
}

export default function AgentSwarmChart({ consensus }: SwarmSignalGaugeProps) {
  if (!consensus || !consensus.symbol) {
    return (
      <div className="flex flex-col items-center justify-center h-[220px] text-gray-500 text-sm space-y-2">
        <Activity className="w-8 h-8 text-gray-600" />
        <span>Waiting for swarm evaluation…</span>
        <span className="text-xs text-gray-600">Agents scan watchlist every cycle</span>
      </div>
    )
  }

  const { direction, confidence, bull_score, bear_score, symbol, trigger_trade, evaluated_at } =
    consensus

  const isBullish = direction === 'bullish'
  const isBearish = direction === 'bearish'

  const bullPct = Math.round(bull_score * 100)
  const bearPct = Math.round(bear_score * 100)
  const total = bullPct + bearPct || 1
  const bullBar = (bullPct / total) * 100
  const bearBar = (bearPct / total) * 100

  const directionColor = isBullish
    ? 'text-emerald-400'
    : isBearish
      ? 'text-red-400'
      : 'text-gray-400'

  const directionBg = isBullish
    ? 'bg-emerald-500/10 border-emerald-500/20'
    : isBearish
      ? 'bg-red-500/10 border-red-500/20'
      : 'bg-gray-500/10 border-gray-500/20'

  const DirectionIcon = isBullish ? TrendingUp : isBearish ? TrendingDown : Minus

  const timeAgo = evaluated_at
    ? (() => {
        const diff = Date.now() - new Date(evaluated_at).getTime()
        const sec = Math.floor(diff / 1000)
        if (sec < 60) return `${sec}s ago`
        if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
        return `${Math.floor(sec / 3600)}h ago`
      })()
    : ''

  return (
    <div className="space-y-4">
      {/* Big Signal */}
      <div
        className={`flex items-center justify-between px-4 py-3 rounded-xl border ${directionBg}`}
      >
        <div className="flex items-center gap-3">
          <DirectionIcon className={`w-6 h-6 ${directionColor}`} />
          <div>
            <div className={`text-lg font-bold ${directionColor}`}>
              {isBullish ? 'BUY' : isBearish ? 'SELL' : 'HOLD'}
            </div>
            <div className="text-xs text-gray-500">
              {symbol} · {confidence}% confidence
            </div>
          </div>
        </div>
        {trigger_trade && (
          <div className="flex items-center gap-1 px-2 py-1 bg-orange-500/15 text-orange-400 rounded-lg text-xs font-medium border border-orange-500/20">
            <Zap className="w-3 h-3" />
            Trade Triggered
          </div>
        )}
      </div>

      {/* Bull / Bear Bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-emerald-400 font-medium">Bull {bullPct}%</span>
          <span className="text-red-400 font-medium">Bear {bearPct}%</span>
        </div>
        <div className="h-2.5 bg-[#1f1f2e] rounded-full overflow-hidden flex">
          <div
            className="h-full bg-emerald-500 transition-all duration-500"
            style={{ width: `${bullBar}%` }}
          />
          <div
            className="h-full bg-red-500 transition-all duration-500"
            style={{ width: `${bearBar}%` }}
          />
        </div>
      </div>

      {/* Meta */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>Consensus: {consensus.consensus_score.toFixed(2)}</span>
        <span>{timeAgo}</span>
      </div>
    </div>
  )
}
