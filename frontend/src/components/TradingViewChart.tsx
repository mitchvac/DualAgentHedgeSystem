import { useEffect, useRef } from 'react'

interface TradingViewChartProps {
  symbol: string
  exchange?: string
  height?: number
}

export default function TradingViewChart({ symbol, exchange = 'OKX', height = 450 }: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    // Convert symbol format: BTC/USDT:USDT → BTCUSDT.P (perpetual futures)
    const base = symbol.split('/')[0]
    const quote = symbol.split('/')[1]?.split(':')[0] || 'USDT'
    const tvSymbol = `${base}${quote}.P`
    const tvExchange = exchange.toUpperCase()

    containerRef.current.innerHTML = ''

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.async = true
    script.type = 'text/javascript'
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: `${tvExchange}:${tvSymbol}`,
      interval: '15',
      timezone: 'Etc/UTC',
      theme: 'dark',
      style: '1',
      locale: 'en',
      enable_publishing: false,
      backgroundColor: 'rgba(17, 17, 24, 1)',
      gridColor: 'rgba(42, 42, 53, 0.5)',
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      calendar: false,
      hide_volume: false,
      support_host: 'https://www.tradingview.com',
    })

    containerRef.current.appendChild(script)
  }, [symbol, exchange])

  return (
    <div
      className="tradingview-widget-container w-full rounded-xl overflow-hidden border border-[#2a2a35]"
      style={{ height }}
    >
      <div
        ref={containerRef}
        className="tradingview-widget-container__widget w-full h-full"
      />
    </div>
  )
}
