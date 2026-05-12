import { useState } from 'react'
import { MonitorUp, MonitorDown, Activity } from 'lucide-react'
import { useExchangeDepth, useExchangePositions, useSystemStatus, useEquity } from '@/hooks/useApi'
import TradingViewChart from '@/components/TradingViewChart'
import OrderEntryForm from '@/components/OrderEntryForm'
import ExchangeDepthPanel from '@/components/ExchangeDepthPanel'
import RecentTrades from '@/components/RecentTrades'
import LivePositions from '@/components/LivePositions'
import { cn } from '@/lib/utils'

export default function ExchangeMonitor() {
  const { data: status } = useSystemStatus()
  const symbol = status?.watchlist?.[0] || 'BTC/USDT:USDT'
  const longEx = 'okx'
  const shortEx = 'bybit'

  const [activeSymbol, setActiveSymbol] = useState(symbol)

  const { data: upDepth, isFetching: upFetching } = useExchangeDepth(activeSymbol, longEx)
  const { data: downDepth, isFetching: downFetching } = useExchangeDepth(activeSymbol, shortEx)
  const { data: upPositions } = useExchangePositions(longEx, activeSymbol)
  const { data: downPositions } = useExchangePositions(shortEx, activeSymbol)
  const { data: equityData } = useEquity()

  const spread = upDepth && downDepth
    ? Math.abs((upDepth.asks[0]?.[0] || 0) - (downDepth.bids[0]?.[0] || 0))
    : 0

  const watchlist = status?.watchlist || ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

  return (
    <div className="space-y-6">
      {/* Header with symbol selector */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Exchange Monitor</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Real-time trading terminal
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Symbol selector */}
          <div className="flex items-center gap-1 bg-[#16161f] border border-[#2a2a35] rounded-lg px-2 py-1">
            {watchlist.map((sym) => (
              <button
                key={sym}
                onClick={() => setActiveSymbol(sym)}
                className={cn(
                  'px-2.5 py-1 rounded text-xs font-medium transition-all',
                  activeSymbol === sym
                    ? 'bg-orange-500/15 text-orange-400'
                    : 'text-gray-500 hover:text-gray-300'
                )}
              >
                {sym.split('/')[0]}
              </button>
            ))}
          </div>
          {spread > 0 && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-[#16161f] border border-[#2a2a35] rounded-lg text-xs text-gray-400">
              <span>Spread</span>
              <span className="text-white font-mono">{spread.toFixed(2)}</span>
            </div>
          )}
          <div className={cn(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium',
            (!upFetching && !downFetching)
              ? 'bg-emerald-500/10 text-emerald-400'
              : 'bg-gray-500/10 text-gray-400'
          )}>
            <Activity className="w-3 h-3" />
            Live
          </div>
        </div>
      </div>

      {/* Chart */}
      <TradingViewChart symbol={activeSymbol} exchange={longEx.toUpperCase()} height={420} />

      {/* Live Positions */}
      <LivePositions
        longPositions={upPositions?.positions || []}
        shortPositions={downPositions?.positions || []}
        equity={equityData?.equity_usdt}
        longExchange={longEx}
        shortExchange={shortEx}
      />

      {/* Split Screen: Order Entry + Depth */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* UP AGENT — Long / Buy */}
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
          <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#2a2a35]">
            <MonitorUp className="w-5 h-5 text-emerald-400" />
            <div>
              <h3 className="text-sm font-semibold text-gray-200">Up Agent</h3>
              <p className="text-[10px] text-gray-500">Long leg · {longEx.toUpperCase()}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Order Entry */}
            <OrderEntryForm
              symbol={activeSymbol}
              exchange={longEx}
              side="buy"
              positions={upPositions?.positions || []}
            />

            {/* Depth + Trades */}
            <div className="space-y-4">
              <ExchangeDepthPanel
                depth={upDepth || null}
                side="bids"
                title="Buy Orders"
                color="green"
              />
              <div className="border-t border-[#2a2a35] pt-3">
                <RecentTrades
                  trades={upDepth?.trades?.filter(t => t.side === 'buy') || []}
                  title="Buy Trades"
                />
              </div>
            </div>
          </div>
        </div>

        {/* DOWN AGENT — Short / Sell */}
        <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] p-5">
          <div className="flex items-center gap-2 mb-4 pb-3 border-b border-[#2a2a35]">
            <MonitorDown className="w-5 h-5 text-red-400" />
            <div>
              <h3 className="text-sm font-semibold text-gray-200">Down Agent</h3>
              <p className="text-[10px] text-gray-500">Short leg · {shortEx.toUpperCase()}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Order Entry */}
            <OrderEntryForm
              symbol={activeSymbol}
              exchange={shortEx}
              side="sell"
              positions={downPositions?.positions || []}
            />

            {/* Depth + Trades */}
            <div className="space-y-4">
              <ExchangeDepthPanel
                depth={downDepth || null}
                side="asks"
                title="Sell Orders"
                color="red"
              />
              <div className="border-t border-[#2a2a35] pt-3">
                <RecentTrades
                  trades={downDepth?.trades?.filter(t => t.side === 'sell') || []}
                  title="Sell Trades"
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
