import { Wifi, WifiOff, LogOut, Bell } from 'lucide-react'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useAuthStore } from '@/store/authStore'
import { cn } from '@/lib/utils'

export default function Header() {
  const { connected } = useWebSocket()
  const { logout, username } = useAuthStore()

  return (
    <header className="h-16 bg-[#0a0a0f]/80 backdrop-blur-xl border-b border-[#1f1f2e] flex items-center justify-between px-6 sticky top-0 z-50">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-medium text-gray-400">
          HedgeSwarm <span className="text-gray-600">v2.0</span>
        </h1>
      </div>

      <div className="flex items-center gap-4">
        <div className={cn(
          'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border',
          connected
            ? 'bg-green-500/10 text-green-400 border-green-500/20'
            : 'bg-red-500/10 text-red-400 border-red-500/20'
        )}>
          {connected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
          {connected ? 'Connected' : 'Disconnected'}
        </div>

        <button className="relative p-2 text-gray-400 hover:text-white transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-orange-500 rounded-full" />
        </button>

        <div className="flex items-center gap-3 pl-4 border-l border-[#1f1f2e]">
          <div className="text-right">
            <div className="text-sm font-medium text-white">{username || 'Trader'}</div>
            <div className="text-xs text-gray-500">Admin</div>
          </div>
          <button
            onClick={logout}
            className="p-2 text-gray-400 hover:text-red-400 transition-colors rounded-lg hover:bg-red-500/10"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>
    </header>
  )
}
