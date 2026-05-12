import { useState, useRef, useCallback } from 'react'
import { X, Search } from 'lucide-react'
import { cn } from '@/lib/utils'

const POPULAR_PAIRS = [
  'BTC/USDT:USDT',
  'ETH/USDT:USDT',
  'SOL/USDT:USDT',
  'XRP/USDT:USDT',
  'DOGE/USDT:USDT',
  'LINK/USDT:USDT',
  'MATIC/USDT:USDT',
  'ADA/USDT:USDT',
  'AVAX/USDT:USDT',
  'DOT/USDT:USDT',
  'LTC/USDT:USDT',
  'BCH/USDT:USDT',
  'ETC/USDT:USDT',
  'UNI/USDT:USDT',
  'ATOM/USDT:USDT',
  'NEAR/USDT:USDT',
  'ARB/USDT:USDT',
  'OP/USDT:USDT',
  'SUI/USDT:USDT',
  'SEI/USDT:USDT',
]

interface WatchlistInputProps {
  value: string
  onChange: (value: string) => void
}

export default function WatchlistInput({ value, onChange }: WatchlistInputProps) {
  const [activeTab, setActiveTab] = useState<'selected' | 'add'>('selected')
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const pairs = value
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)

  const addPair = useCallback(
    (pair: string) => {
      const trimmed = pair.trim().toUpperCase()
      if (!trimmed) return
      const current = pairs
      if (current.includes(trimmed)) return
      const newValue = [...current, trimmed].join(', ')
      onChange(newValue)
      setInputValue('')
    },
    [pairs, onChange]
  )

  const removePair = useCallback(
    (pair: string) => {
      const newValue = pairs.filter((p) => p !== pair).join(', ')
      onChange(newValue)
    },
    [pairs, onChange]
  )

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addPair(inputValue)
      setInputValue('')
    }
    if (e.key === 'Backspace' && inputValue === '' && pairs.length > 0) {
      removePair(pairs[pairs.length - 1])
    }
  }

  const filteredSuggestions = POPULAR_PAIRS.filter(
    (p) =>
      !pairs.includes(p) &&
      (inputValue === '' || p.toLowerCase().includes(inputValue.toLowerCase()))
  )

  const availablePairs = POPULAR_PAIRS.filter((p) => !pairs.includes(p))

  return (
    <div className="bg-[#16161f] rounded-2xl border border-[#2a2a35] overflow-hidden">
      {/* Header */}
      <div className="px-5 pt-5 pb-0">
        <h3 className="text-sm font-semibold text-gray-200">Watchlist</h3>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-6 px-5 mt-4 border-b border-[#2a2a35]">
        <button
          type="button"
          onClick={() => setActiveTab('selected')}
          className={cn(
            'pb-3 text-sm font-medium transition-all border-b-2',
            activeTab === 'selected'
              ? 'text-orange-400 border-orange-500'
              : 'text-gray-500 border-transparent hover:text-gray-400'
          )}
        >
          Selected ({pairs.length})
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab('add')
            setTimeout(() => inputRef.current?.focus(), 50)
          }}
          className={cn(
            'pb-3 text-sm font-medium transition-all border-b-2',
            activeTab === 'add'
              ? 'text-orange-400 border-orange-500'
              : 'text-gray-500 border-transparent hover:text-gray-400'
          )}
        >
          Add Pairs
        </button>
      </div>

      {/* Selected Tab */}
      {activeTab === 'selected' && (
        <div className="p-5">
          {pairs.length === 0 ? (
            <div className="text-center py-8">
              <div className="text-sm text-gray-500">No pairs selected</div>
              <button
                type="button"
                onClick={() => setActiveTab('add')}
                className="mt-2 text-xs text-orange-400 hover:text-orange-300 transition-colors"
              >
                Add pairs →
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {pairs.map((pair) => {
                const base = pair.split('/')[0]
                return (
                  <span
                    key={pair}
                    className="inline-flex items-center gap-2 text-sm font-medium text-orange-400"
                  >
                    <span className="uppercase tracking-wide">{base}</span>
                    <button
                      type="button"
                      onClick={() => removePair(pair)}
                      className="text-gray-500 hover:text-red-400 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </span>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Pairs Tab */}
      {activeTab === 'add' && (
        <div className="p-5 space-y-4">
          {/* Search input */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search or type symbol..."
              className="w-full bg-[#0a0a0f] border border-[#2a2a35] rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/20 transition-all"
            />
            {inputValue && (
              <button
                type="button"
                onClick={() => {
                  addPair(inputValue)
                  setInputValue('')
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 bg-orange-500 hover:bg-orange-400 rounded-lg text-xs font-medium text-white transition-colors"
              >
                Add
              </button>
            )}
          </div>

          {/* Suggestions or popular grid */}
          <div>
            <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2.5">
              {inputValue ? 'Matching pairs' : 'Popular pairs'}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {(inputValue ? filteredSuggestions : availablePairs).map((pair) => {
                const base = pair.split('/')[0]
                return (
                  <button
                    key={pair}
                    type="button"
                    onClick={() => addPair(pair)}
                    className="px-2 py-1.5 text-sm font-medium text-orange-400 hover:text-orange-300 transition-colors"
                  >
                    + {base}
                  </button>
                )
              })}
              {(inputValue ? filteredSuggestions : availablePairs).length === 0 && (
                <div className="text-sm text-gray-500 py-2">
                  {inputValue ? 'No matching pairs found' : 'All popular pairs added'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
