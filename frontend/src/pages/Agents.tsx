import { useState } from 'react'
import { Play, Pause, Trophy, Target, BarChart3 } from 'lucide-react'
import AgentGrid from '@/components/AgentGrid'
import { useAgents, useAgentAccuracy } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useCommand } from '@/hooks/useApi'
import { cn } from '@/lib/utils'

const filters = [
  { key: 'All', label: 'All' },
  { key: 'sentiment', label: 'Sentiment' },
  { key: 'technical', label: 'Technical' },
  { key: 'volatility', label: 'Volatility' },
  { key: 'onchain', label: 'OnChain' },
  { key: 'funding', label: 'Funding' },
  { key: 'orderflow', label: 'OrderFlow' },
  { key: 'macro', label: 'Macro' },
  { key: 'news', label: 'News' },
  { key: 'reflection', label: 'Reflection' },
]

export default function Agents() {
  const { data } = useAgents()
  const { agents: wsAgents } = useWebSocket()
  const [activeFilter, setActiveFilter] = useState('All')
  const command = useCommand()
  const { data: accuracyData } = useAgentAccuracy(30)

  const allAgents = wsAgents.length > 0 ? wsAgents : data?.agents || []

  const filtered = activeFilter === 'All'
    ? allAgents
    : allAgents.filter((a) => a.role === activeFilter)

  const workingCount = allAgents.filter((a) => a.status === 'working').length
  const accuracy = accuracyData?.accuracy || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Agent Swarm</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {allAgents.length} specialized AI agents · {workingCount} active
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => command.mutate({ command: 'launch_swarm' })}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-orange-500 to-orange-600 rounded-xl text-sm font-medium text-white hover:from-orange-400 hover:to-orange-500 transition-all shadow-lg shadow-orange-500/20"
          >
            <Play className="w-4 h-4" />
            Launch
          </button>
          <button
            onClick={() => command.mutate({ command: 'pause_swarm' })}
            className="flex items-center gap-2 px-4 py-2 bg-[#16161f] border border-[#2a2a35] rounded-xl text-sm text-gray-300 hover:border-gray-600 transition-all"
          >
            <Pause className="w-4 h-4" />
            Pause
          </button>
        </div>
      </div>

      {/* Accuracy Leaderboard */}
      {accuracy.length > 0 && (
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
          <div className="flex items-center gap-2 mb-4">
            <Trophy className="w-5 h-5 text-yellow-400" />
            <h3 className="text-sm font-semibold text-gray-200">Agent Accuracy Leaderboard</h3>
            <span className="text-xs text-gray-500 ml-auto">Last 30 days</span>
          </div>
          <div className="space-y-2">
            {accuracy.map((a, i) => (
              <div key={a.role} className="flex items-center justify-between bg-[#0a0a0f] rounded-lg px-3 py-2">
                <div className="flex items-center gap-3">
                  <span className={cn(
                    'w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold',
                    i === 0 ? 'bg-yellow-500/20 text-yellow-400' :
                    i === 1 ? 'bg-gray-500/20 text-gray-300' :
                    i === 2 ? 'bg-orange-500/20 text-orange-400' :
                    'bg-[#1a1a24] text-gray-500'
                  )}>
                    {i + 1}
                  </span>
                  <span className="text-sm text-gray-300 capitalize">{a.role.toLowerCase()}</span>
                </div>
                <div className="flex items-center gap-4 text-xs">
                  <div className="flex items-center gap-1">
                    <Target className="w-3 h-3 text-gray-500" />
                    <span className="text-gray-400">{a.correct_votes}/{a.total_votes}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <BarChart3 className="w-3 h-3 text-gray-500" />
                    <span className={a.accuracy_pct >= 60 ? 'text-emerald-400' : 'text-orange-400'}>
                      {a.accuracy_pct}%
                    </span>
                  </div>
                  <div className="w-20 bg-[#1a1a24] rounded-full h-1.5 overflow-hidden">
                    <div
                      className={cn('h-full rounded-full', a.accuracy_pct >= 60 ? 'bg-emerald-500' : 'bg-orange-500')}
                      style={{ width: `${a.accuracy_pct}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setActiveFilter(f.key)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
              activeFilter === f.key
                ? 'bg-orange-500/15 text-orange-400 border-orange-500/30'
                : 'bg-[#16161f] text-gray-400 border-[#2a2a35] hover:border-gray-600'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <AgentGrid agents={filtered} />
    </div>
  )
}
