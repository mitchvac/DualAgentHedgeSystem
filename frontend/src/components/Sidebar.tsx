import { useLocation, useNavigate, Link } from 'react-router-dom'
import {
  LayoutDashboard,
  BarChart3,
  Bot,
  Monitor,
  Settings,
  TrendingUp,
  Shield,
  PieChart,
  Activity,
  Trophy,
  Wallet,
  CreditCard,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useSystemStatus } from '@/hooks/useApi'
import Tooltip from './Tooltip'

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/', tooltip: 'Main overview with live PnL, positions, and swarm consensus' },
  { icon: PieChart, label: 'Portfolio', path: '/portfolio', tooltip: 'Equity curve, monthly returns, and capital growth over time' },
  { icon: Activity, label: 'Analytics', path: '/analytics', tooltip: 'Sharpe/Sortino ratios, drawdowns, win streaks, and strategy performance' },
  { icon: BarChart3, label: 'Trades', path: '/trades', tooltip: 'Full trade history with expandable leg details and PnL breakdown' },
  { icon: Bot, label: 'Agents', path: '/agents', tooltip: 'Live agent swarm status, consensus scores, and agent roster' },
  { icon: Trophy, label: 'Leaderboard', path: '/leaderboard', tooltip: 'Per-agent win/loss tracking and prediction accuracy by role' },
  { icon: Monitor, label: 'Exchange', path: '/exchange-monitor', tooltip: 'Exchange health, order book depth, and balance monitoring' },
  { icon: Wallet, label: 'Wallet', path: '/wallet', tooltip: 'Connect crypto wallet, view balances, and fund your trading account' },
  { icon: CreditCard, label: 'Billing', path: '/billing', tooltip: 'Subscription status and crypto payment options' },
  { icon: Settings, label: 'Settings', path: '/settings', tooltip: 'Risk limits, agent counts, watchlist, and trading mode configuration' },
]

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { data: status } = useSystemStatus()

  const isPaper = status?.paper_trading ?? true

  return (
    <aside className="w-64 bg-[#111118] border-r border-[#1f1f2e] flex flex-col">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-orange-500 to-orange-600 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-white" />
          </div>
          <span className="text-lg font-bold text-white">HedgeSwarm</span>
        </div>
        <p className="text-xs text-gray-500 ml-12">Dual-Agent Hedge</p>
      </div>

      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          return (
            <Tooltip key={item.path} content={item.tooltip} position="right">
              <button
                onClick={() => navigate(item.path)}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200',
                  isActive
                    ? 'bg-orange-500/10 text-orange-400'
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                )}
              >
                <item.icon className={cn('w-5 h-5', isActive && 'text-orange-400')} />
                {item.label}
              </button>
            </Tooltip>
          )
        })}
      </nav>

      <div className="p-4 border-t border-[#1f1f2e]">
        <Link to="/settings" className="block">
          <div className="bg-[#16161f] rounded-xl p-4 border border-[#2a2a35] hover:border-orange-500/30 transition-all cursor-pointer group">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-gray-400 group-hover:text-orange-400 transition-colors" />
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider group-hover:text-orange-400 transition-colors">Mode</span>
              <span className="ml-auto text-[10px] text-gray-600 group-hover:text-orange-400 transition-colors">Click to change</span>
            </div>
            <div className={cn(
              'text-sm font-bold',
              isPaper ? 'text-green-400' : 'text-red-400'
            )}>
              {isPaper ? '📝 PAPER TRADING' : '🔴 LIVE TRADING'}
            </div>
            <div className="text-xs text-gray-500 mt-1">Refresh: 10s</div>
          </div>
        </Link>
      </div>
    </aside>
  )
}
