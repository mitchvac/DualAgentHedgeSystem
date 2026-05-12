import { useState } from 'react'
import { Trophy, Target, TrendingUp, TrendingDown, Brain, Zap, Shield, Activity } from 'lucide-react'
import Tooltip from '@/components/Tooltip'
import { useAgents, useAnalytics } from '@/hooks/useApi'
import { cn } from '@/lib/utils'

const ROLE_ICONS: Record<string, React.ReactNode> = {
  SENTIMENT: <Brain className="w-4 h-4" />,
  TECHNICAL: <Activity className="w-4 h-4" />,
  VOLATILITY: <Zap className="w-4 h-4" />,
  ONCHAIN: <Shield className="w-4 h-4" />,
  FUNDING: <TrendingUp className="w-4 h-4" />,
  ORDERFLOW: <Target className="w-4 h-4" />,
  MACRO: <TrendingDown className="w-4 h-4" />,
  NEWS: <Brain className="w-4 h-4" />,
  REFLECTION: <Activity className="w-4 h-4" />,
}

const ROLE_COLORS: Record<string, string> = {
  SENTIMENT: 'text-purple-400 bg-purple-400/10',
  TECHNICAL: 'text-blue-400 bg-blue-400/10',
  VOLATILITY: 'text-orange-400 bg-orange-400/10',
  ONCHAIN: 'text-emerald-400 bg-emerald-400/10',
  FUNDING: 'text-cyan-400 bg-cyan-400/10',
  ORDERFLOW: 'text-pink-400 bg-pink-400/10',
  MACRO: 'text-yellow-400 bg-yellow-400/10',
  NEWS: 'text-indigo-400 bg-indigo-400/10',
  REFLECTION: 'text-gray-400 bg-gray-400/10',
}

export default function Leaderboard() {
  const { data: agentsData } = useAgents()
  const { data: analytics } = useAnalytics()
  const [filter, setFilter] = useState<string>('all')

  const agents = agentsData?.agents || []

  // Group by role and compute mock accuracy (in a real system this would come from backend)
  const roleGroups = agents.reduce((acc, agent) => {
    const role = agent.role
    if (!acc[role]) acc[role] = []
    acc[role].push(agent)
    return acc
  }, {} as Record<string, typeof agents>)

  const roles = Object.keys(roleGroups).sort()
  const filteredRoles = filter === 'all' ? roles : roles.filter((r) => r === filter)

  // Mock accuracy per role (would be real data from backend)
  const roleAccuracy: Record<string, number> = {
    SENTIMENT: 62,
    TECHNICAL: 71,
    VOLATILITY: 58,
    ONCHAIN: 65,
    FUNDING: 74,
    ORDERFLOW: 68,
    MACRO: 55,
    NEWS: 60,
    REFLECTION: 77,
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Trophy className="w-7 h-7 text-orange-400" />
            Agent Accuracy Leaderboard
          </h1>
          <p className="text-sm text-gray-500 mt-1">Per-agent win/loss tracking and prediction accuracy by role</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-[#16161f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-gray-300"
          >
            <option value="all">All Roles</option>
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <Tooltip content="Total number of AI agents in the swarm across all roles">
            <div className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Total Agents</div>
          </Tooltip>
          <div className="text-2xl font-bold text-white mt-1">{agents.length}</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <Tooltip content="Average prediction accuracy across all agent roles">
            <div className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Avg Accuracy</div>
          </Tooltip>
          <div className="text-2xl font-bold text-emerald-400 mt-1">
            {roles.length > 0
              ? (roles.reduce((sum, r) => sum + (roleAccuracy[r] || 50), 0) / roles.length).toFixed(1)
              : '—'}%
          </div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <Tooltip content="Percentage of closed trades that were profitable">
            <div className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Win Rate</div>
          </Tooltip>
          <div className="text-2xl font-bold text-blue-400 mt-1">{analytics?.win_rate?.toFixed(1) ?? '—'}%</div>
        </div>
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
          <Tooltip content="Gross profit divided by gross loss. >1.5 is considered good">
            <div className="text-xs text-gray-500 uppercase tracking-wider cursor-help">Profit Factor</div>
          </Tooltip>
          <div className="text-2xl font-bold text-orange-400 mt-1">{analytics?.profit_factor?.toFixed(2) ?? '—'}</div>
        </div>
      </div>

      {/* Role Leaderboards */}
      <div className="space-y-4">
        {filteredRoles.map((role) => {
          const roleAgents = roleGroups[role]
          const accuracy = roleAccuracy[role] || 50
          const colorClass = ROLE_COLORS[role] || 'text-gray-400 bg-gray-400/10'
          return (
            <div key={role} className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={cn('p-2 rounded-lg', colorClass)}>
                    {ROLE_ICONS[role] || <Brain className="w-4 h-4" />}
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-white">{role}</h3>
                    <p className="text-xs text-gray-500">{roleAgents.length} agents</p>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold text-white">{accuracy}%</div>
                  <div className="text-xs text-gray-500">avg accuracy</div>
                </div>
              </div>

              {/* Agent list */}
              <div className="space-y-2">
                {roleAgents.slice(0, 10).map((agent, i) => (
                  <div
                    key={agent.agent_id}
                    className="flex items-center justify-between bg-[#0a0a0f] rounded-lg px-4 py-2.5"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 w-5">{i + 1}</span>
                      <span className="text-xs font-mono text-gray-400">{agent.agent_id}</span>
                      <span className="text-xs text-gray-500">{agent.task?.slice(0, 40)}...</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className={cn('text-xs font-medium', agent.status === 'active' ? 'text-emerald-400' : 'text-gray-500')}>
                        {agent.status}
                      </span>
                      <div className="w-24 h-1.5 bg-[#1f1f2e] rounded-full overflow-hidden">
                        <div
                          className={cn('h-full rounded-full', accuracy >= 70 ? 'bg-emerald-400' : accuracy >= 55 ? 'bg-orange-400' : 'bg-red-400')}
                          style={{ width: `${accuracy + (Math.random() * 20 - 10)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
