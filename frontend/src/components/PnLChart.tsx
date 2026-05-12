import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { formatCurrency } from '@/lib/utils'

interface ChartData {
  date: string
  pnl: number
}

interface PnLChartProps {
  data: ChartData[]
  height?: number
}

export default function PnLChart({ data, height = 350 }: PnLChartProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-[350px] text-gray-500 text-sm">
        No trade data available
      </div>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f1f2e" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#6b7280', fontSize: 12 }}
          tickLine={false}
          axisLine={{ stroke: '#2a2a35' }}
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 12 }}
          tickLine={false}
          axisLine={{ stroke: '#2a2a35' }}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1a1a24',
            border: '1px solid #2a2a35',
            borderRadius: '12px',
            color: '#e5e7eb',
          }}
          formatter={(value: number) => [formatCurrency(value), 'PnL']}
        />
        <Area
          type="monotone"
          dataKey="pnl"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#pnlGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
