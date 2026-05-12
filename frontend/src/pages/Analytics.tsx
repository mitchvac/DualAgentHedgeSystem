import { useAnalytics, useAdvancedAnalytics } from '@/hooks/useApi'
import { formatCurrency, cn } from '@/lib/utils'
import { TrendingUp, TrendingDown, Zap, Target, Activity, BarChart3, Trophy, AlertTriangle } from 'lucide-react'
import Tooltip from '@/components/Tooltip'

export default function Analytics() {
  const { data: basic } = useAnalytics()
  const { data: adv } = useAdvancedAnalytics()

  const metrics = [
    {
      label: 'Sharpe Ratio',
      value: adv?.sharpe_ratio ?? 0,
      icon: <BarChart3 className="w-4 h-4 text-blue-400" />,
      format: (v: number) => v.toFixed(2),
      good: (v: number) => v > 1,
      desc: 'Risk-adjusted return ( >1 good, >2 great)',
    },
    {
      label: 'Sortino Ratio',
      value: adv?.sortino_ratio ?? 0,
      icon: <Activity className="w-4 h-4 text-purple-400" />,
      format: (v: number) => v.toFixed(2),
      good: (v: number) => v > 1,
      desc: 'Downside risk-adjusted return',
    },
    {
      label: 'Max Drawdown',
      value: adv?.max_drawdown_pct ?? 0,
      icon: <AlertTriangle className="w-4 h-4 text-red-400" />,
      format: (v: number) => `${v.toFixed(2)}%`,
      good: (v: number) => v < 10,
      desc: 'Worst peak-to-trough decline',
    },
    {
      label: 'Recovery Factor',
      value: adv?.recovery_factor ?? 0,
      icon: <Zap className="w-4 h-4 text-yellow-400" />,
      format: (v: number) => v.toFixed(2),
      good: (v: number) => v > 2,
      desc: 'Profit vs max drawdown ( >2 good)',
    },
    {
      label: 'Expectancy',
      value: adv?.expectancy ?? 0,
      icon: <Target className="w-4 h-4 text-emerald-400" />,
      format: (v: number) => formatCurrency(v),
      good: (v: number) => v > 0,
      desc: 'Average expected return per trade',
    },
    {
      label: 'Profit Factor',
      value: basic?.profit_factor ?? 0,
      icon: <TrendingUp className="w-4 h-4 text-orange-400" />,
      format: (v: number) => v.toFixed(2),
      good: (v: number) => v > 1.5,
      desc: 'Gross profit / gross loss ( >1.5 good)',
    },
  ]

  const streaks = [
    {
      label: 'Longest Win Streak',
      value: adv?.longest_win_streak ?? 0,
      icon: <Trophy className="w-4 h-4 text-emerald-400" />,
      color: 'text-emerald-400',
    },
    {
      label: 'Longest Loss Streak',
      value: adv?.longest_loss_streak ?? 0,
      icon: <TrendingDown className="w-4 h-4 text-red-400" />,
      color: 'text-red-400',
    },
    {
      label: 'Current Streak',
      value: adv?.current_streak ?? 0,
      icon: <Activity className="w-4 h-4 text-blue-400" />,
      color: adv?.current_streak_type === 'win' ? 'text-emerald-400' : 'text-red-400',
    },
  ]

  const extremes = [
    { label: 'Best Trade', value: adv?.best_trade ?? 0, color: 'text-emerald-400' },
    { label: 'Worst Trade', value: adv?.worst_trade ?? 0, color: 'text-red-400' },
    { label: 'Avg Trade', value: adv?.avg_trade ?? 0, color: 'text-gray-200' },
    { label: 'Avg Win', value: basic?.avg_win ?? 0, color: 'text-emerald-400' },
    { label: 'Avg Loss', value: basic?.avg_loss ?? 0, color: 'text-red-400' },
    { label: 'Win Rate', value: basic ? `${basic.win_rate}%` : '0%', color: 'text-blue-400' },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Performance Analytics</h2>
        <p className="text-sm text-gray-500 mt-0.5">Deep metrics on your trading performance</p>
      </div>

      {/* Core Metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {metrics.map((m) => (
          <div key={m.label} className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-4">
            <div className="flex items-center gap-2 mb-2">
              {m.icon}
              <Tooltip content={m.desc}>
                <span className="text-xs text-gray-500 uppercase tracking-wider cursor-help">{m.label}</span>
              </Tooltip>
            </div>
            <div className={cn('text-2xl font-bold', m.good(m.value) ? 'text-emerald-400' : 'text-orange-400')}>
              {m.format(m.value)}
            </div>
            <div className="text-[10px] text-gray-600 mt-1">{m.desc}</div>
          </div>
        ))}
      </div>

      {/* Streaks */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
        <h3 className="text-sm font-semibold text-gray-200 mb-4">Streaks</h3>
        <div className="grid grid-cols-3 gap-4">
          {streaks.map((s) => (
            <div key={s.label} className="bg-[#0a0a0f] rounded-xl p-4 text-center">
              <div className="flex items-center justify-center gap-2 mb-2">
                {s.icon}
                <span className="text-xs text-gray-500">{s.label}</span>
              </div>
              <div className={cn('text-xl font-bold', s.color)}>{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Trade Extremes */}
      <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
        <h3 className="text-sm font-semibold text-gray-200 mb-4">Trade Statistics</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {extremes.map((e) => (
            <div key={e.label} className="bg-[#0a0a0f] rounded-xl p-3 text-center">
              <div className="text-[10px] text-gray-500 mb-1">{e.label}</div>
              <div className={cn('text-sm font-bold', e.color)}>
                {typeof e.value === 'number' ? formatCurrency(e.value) : e.value}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
