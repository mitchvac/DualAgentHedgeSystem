import { cn, formatPercentage } from '@/lib/utils'
import { TrendingUp, TrendingDown, Minus, HelpCircle } from 'lucide-react'
import Tooltip from './Tooltip'

interface KPICardProps {
  title: string
  value: string | number
  subtitle?: string
  delta?: number
  deltaLabel?: string
  icon: React.ReactNode
  color?: 'green' | 'red' | 'blue' | 'orange' | 'purple'
  className?: string
  tooltip?: string
}

const colorMap = {
  green: 'from-emerald-500/20 to-emerald-600/5 border-emerald-500/30',
  red: 'from-red-500/20 to-red-600/5 border-red-500/30',
  blue: 'from-blue-500/20 to-blue-600/5 border-blue-500/30',
  orange: 'from-orange-500/20 to-orange-600/5 border-orange-500/30',
  purple: 'from-purple-500/20 to-purple-600/5 border-purple-500/30',
}

export default function KPICard({
  title,
  value,
  subtitle,
  delta,
  deltaLabel,
  icon,
  color = 'blue',
  className,
  tooltip,
}: KPICardProps) {
  const isPositive = delta !== undefined && delta >= 0
  const isNegative = delta !== undefined && delta < 0

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]',
        colorMap[color],
        className
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="p-2 rounded-lg bg-white/5">{icon}</div>
        {delta !== undefined && (
          <div
            className={cn(
              'flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold',
              isPositive && 'bg-emerald-500/15 text-emerald-400',
              isNegative && 'bg-red-500/15 text-red-400',
              !isPositive && !isNegative && 'bg-gray-500/15 text-gray-400'
            )}
          >
            {isPositive && <TrendingUp className="w-3 h-3" />}
            {isNegative && <TrendingDown className="w-3 h-3" />}
            {!isPositive && !isNegative && <Minus className="w-3 h-3" />}
            {deltaLabel || formatPercentage(delta)}
          </div>
        )}
      </div>

      <div className="text-2xl font-bold text-white mb-1">{value}</div>
      <div className="flex items-center gap-1.5">
        <div className="text-xs text-gray-400 font-medium uppercase tracking-wider">{title}</div>
        {tooltip && (
          <Tooltip content={tooltip}>
            <HelpCircle className="w-3 h-3 text-gray-600 hover:text-gray-400 cursor-help" />
          </Tooltip>
        )}
      </div>
      {subtitle && <div className="text-xs text-gray-500 mt-1">{subtitle}</div>}
    </div>
  )
}
