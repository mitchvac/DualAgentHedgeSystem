import { Shield, Sword } from 'lucide-react'
import type { DefenseStatus } from '@/types'
import { cn } from '@/lib/utils'

interface DefensePanelProps {
  defense: DefenseStatus | null
}

export default function DefensePanel({ defense }: DefensePanelProps) {
  if (!defense) {
    return (
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-6 text-center">
        <Shield className="w-8 h-8 text-gray-600 mx-auto mb-3" />
        <div className="text-sm text-gray-400">Defense Swarm not running</div>
        <div className="text-xs text-gray-600 mt-1">Start the trading engine to activate</div>
      </div>
    )
  }

  const { active, circuit_broken, bull_score, total_events, rotations_today, stealth_splits_today, events } = defense

  const statusColor = circuit_broken ? 'text-red-400' : active ? 'text-emerald-400' : 'text-gray-400'
  const statusText = circuit_broken ? '🔴 CIRCUIT BROKEN' : active ? '⚔️ ACTIVE' : '💤 STANDBY'

  return (
    <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sword className="w-5 h-5 text-orange-400" />
          <span className="text-sm font-semibold text-gray-200">Defense Swarm</span>
        </div>
        <span className={cn('text-xs font-bold', statusColor)}>{statusText}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-[#0a0a0f] rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Bull Score</div>
          <div className="text-lg font-bold text-white">{bull_score.toFixed(2)}</div>
        </div>
        <div className="bg-[#0a0a0f] rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Events</div>
          <div className="text-lg font-bold text-white">{total_events}</div>
        </div>
        <div className="bg-[#0a0a0f] rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Rotations</div>
          <div className="text-lg font-bold text-white">{rotations_today}</div>
        </div>
        <div className="bg-[#0a0a0f] rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Stealth Splits</div>
          <div className="text-lg font-bold text-white">{stealth_splits_today}</div>
        </div>
      </div>

      {events && events.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Recent Events</div>
          <div className="space-y-1.5">
            {events.slice(0, 5).map((e, i) => (
              <div key={i} className="flex items-center justify-between bg-[#0a0a0f] rounded-lg px-3 py-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-gray-500">{e.time}</span>
                  <span className="text-gray-300">{e.exchange}</span>
                  <span className="px-1.5 py-0.5 rounded bg-orange-500/15 text-orange-400 text-[10px] font-semibold">
                    {e.type}
                  </span>
                </div>
                <span className="text-orange-400 font-medium">{e.action}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
