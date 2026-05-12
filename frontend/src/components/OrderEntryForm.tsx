import { useState } from 'react'
import { TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import { usePlaceOrder, useExchangeBalance } from '@/hooks/useApi'
import { cn } from '@/lib/utils'
import type { ExchangePosition } from '@/types'

interface OrderEntryFormProps {
  symbol: string
  exchange: string
  side: 'buy' | 'sell'
  positions: ExchangePosition[]
  onOrderPlaced?: () => void
}

export default function OrderEntryForm({ symbol, exchange, side, positions, onOrderPlaced }: OrderEntryFormProps) {
  const [price, setPrice] = useState('')
  const [amount, setAmount] = useState('')
  const [leverage, setLeverage] = useState(5)
  const [tpSl, setTpSl] = useState(false)
  const placeOrder = usePlaceOrder()

  const asset = symbol.split('/')[0]
  const quoteAsset = symbol.split('/')[1]?.split(':')[0] || 'USDT'
  const { data: balance } = useExchangeBalance(exchange, side === 'buy' ? quoteAsset : asset)

  const isBuy = side === 'buy'
  const position = positions.find(p => p.symbol === symbol)

  const handleSubmit = async () => {
    const amt = parseFloat(amount)
    if (!amt || amt <= 0) return
    await placeOrder.mutateAsync({
      exchange,
      symbol,
      side,
      amount: amt,
      leverage,
    })
    setAmount('')
    onOrderPlaced?.()
  }

  const setMaxAmount = () => {
    if (!balance) return
    if (isBuy) {
      // Rough estimate: balance / price
      setAmount((balance.free * 0.95).toFixed(4))
    } else {
      setAmount(balance.free.toFixed(4))
    }
  }

  return (
    <div className="space-y-3">
      {/* Position Summary */}
      {position && (
        <div className={cn(
          'rounded-lg px-3 py-2 text-xs border',
          position.side === 'long' || position.side === 'buy'
            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
            : 'bg-red-500/10 border-red-500/20 text-red-400'
        )}>
          <div className="flex items-center justify-between">
            <span>Open {position.side.toUpperCase()}</span>
            <span className="font-mono">{position.contracts.toFixed(4)} {asset}</span>
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-gray-500">Entry</span>
            <span className="font-mono">{position.entry_price.toFixed(4)}</span>
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-gray-500">PnL</span>
            <span className={cn(
              'font-mono font-bold',
              position.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'
            )}>
              {position.unrealized_pnl >= 0 ? '+' : ''}{position.unrealized_pnl.toFixed(2)} USDT
            </span>
          </div>
        </div>
      )}

      {/* Price Input */}
      <div className="space-y-1">
        <label className="text-[10px] text-gray-500 uppercase tracking-wider">Price</label>
        <div className="relative">
          <input
            type="number"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="Market"
            className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-gray-500 font-mono"
          />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">{quoteAsset}</span>
        </div>
      </div>

      {/* Amount Input */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label className="text-[10px] text-gray-500 uppercase tracking-wider">Amount</label>
          <button
            onClick={setMaxAmount}
            className="text-[10px] text-orange-400 hover:text-orange-300 transition-colors"
          >
            MAX
          </button>
        </div>
        <div className="relative">
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-gray-500 font-mono"
          />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-500">{asset}</span>
        </div>
      </div>

      {/* Leverage Slider */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <label className="text-[10px] text-gray-500 uppercase tracking-wider">Leverage</label>
          <span className="text-xs text-white font-mono">{leverage}x</span>
        </div>
        <input
          type="range"
          min={1}
          max={20}
          value={leverage}
          onChange={(e) => setLeverage(parseInt(e.target.value))}
          className="w-full h-1.5 bg-[#2a2a35] rounded-lg appearance-none cursor-pointer accent-orange-500"
        />
        <div className="flex justify-between text-[10px] text-gray-600">
          <span>1x</span>
          <span>10x</span>
          <span>20x</span>
        </div>
      </div>

      {/* TP/SL Toggle */}
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={`tpsl-${side}`}
          checked={tpSl}
          onChange={(e) => setTpSl(e.target.checked)}
          className="w-4 h-4 rounded border-[#2a2a35] bg-[#0a0a0f] text-orange-500 focus:ring-orange-500"
        />
        <label htmlFor={`tpsl-${side}`} className="text-xs text-gray-400">TP / SL</label>
      </div>

      {/* Balance */}
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>Available</span>
        <span className="text-white font-mono">{balance?.free.toFixed(4) ?? '—'} {side === 'buy' ? quoteAsset : asset}</span>
      </div>

      {/* Submit Button */}
      <button
        onClick={handleSubmit}
        disabled={placeOrder.isPending || !amount}
        className={cn(
          'w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-bold transition-all disabled:opacity-50',
          isBuy
            ? 'bg-emerald-500 hover:bg-emerald-400 text-white'
            : 'bg-red-500 hover:bg-red-400 text-white'
        )}
      >
        {placeOrder.isPending ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : isBuy ? (
          <TrendingUp className="w-4 h-4" />
        ) : (
          <TrendingDown className="w-4 h-4" />
        )}
        {isBuy ? 'Buy' : 'Sell'} {asset}
      </button>
    </div>
  )
}
