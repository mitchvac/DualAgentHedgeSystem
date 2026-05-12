import { Activity } from 'lucide-react'
import type { Agent } from '@/types'
import { cn } from '@/lib/utils'

interface AgentGridProps {
  agents: Agent[]
}

const roleColors: Record<string, string> = {
  SENTIMENT: 'border-l-pink-500',
  TECHNICAL: 'border-l-blue-500',
  VOLATILITY: 'border-l-purple-500',
  ONCHAIN: 'border-l-cyan-500',
  FUNDING: 'border-l-yellow-500',
  ORDERFLOW: 'border-l-orange-500',
  MACRO: 'border-l-red-500',
  NEWS: 'border-l-green-500',
  REFLECTION: 'border-l-indigo-500',
  SUPERVISOR: 'border-l-white',
  UP_AGENT: 'border-l-emerald-500',
  DOWN_AGENT: 'border-l-rose-500',
}

export default function AgentGrid({ agents }: AgentGridProps) {
  if (!agents.length) {
    return (
      <div className="text-center py-12 text-gray-500 text-sm">
        No agents loaded
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
      {agents.map((agent) => {
        const isWorking = agent.status === 'working'
        return (
          <div
            key={agent.agent_id}
            className={cn(
              'bg-[#16161f] rounded-xl p-4 border border-[#2a2a35] border-l-4 transition-all duration-200 hover:border-[#f97316] hover:-translate-y-0.5',
              roleColors[agent.role] || 'border-l-gray-500'
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
                {agent.role} · wt {agent.weight}x
              </span>
              {isWorking && (
                <Activity className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
              )}
            </div>
            <div className="text-sm font-semibold text-gray-200 mb-1">{agent.agent_id}</div>
            <div className="flex items-center gap-2 mb-2">
              <span
                className={cn(
                  'w-2 h-2 rounded-full',
                  isWorking ? 'bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-gray-500'
                )}
              />
              <span className={cn('text-xs font-medium', isWorking ? 'text-emerald-400' : 'text-gray-500')}>
                {isWorking ? 'WORKING' : 'IDLE'}
              </span>
            </div>
            <div className="text-xs text-gray-500">{agent.task}</div>
          </div>
        )
      })}
    </div>
  )
}
