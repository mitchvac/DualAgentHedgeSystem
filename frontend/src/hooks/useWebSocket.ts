import { useEffect, useRef, useState, useCallback } from 'react'
import type { WSMessage, Trade, DefenseStatus, Agent, Position, SwarmConsensus } from '@/types'
import { getAuthToken } from '@/lib/supabase'

export function useWebSocket() {
  const [connected, setConnected] = useState(false)
  const [trades, setTrades] = useState<Trade[]>([])
  const [defense, setDefense] = useState<DefenseStatus | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [equity, setEquity] = useState<number | null>(null)
  const [consensus, setConsensus] = useState<SwarmConsensus | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const token = await getAuthToken()
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/ws?token=${encodeURIComponent(token)}`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data)
        if (msg.type === 'init' || msg.type === 'update') {
          if (msg.trades) setTrades(msg.trades)
          if (msg.defense !== undefined) setDefense(msg.defense)
          if (msg.agents) setAgents(msg.agents)
          if (msg.positions) setPositions(msg.positions)
          if (msg.equity !== undefined) setEquity(msg.equity)
          if (msg.consensus !== undefined) setConsensus(msg.consensus)
        }
      } catch (err) {
        console.error('[WS] Parse error:', err)
      }
    }

    ws.onclose = (ev) => {
      setConnected(false)
      wsRef.current = null
      // Don't reconnect on auth failure (code 4001)
      if (ev.code === 4001) return
      reconnectTimer.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [])

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    connect()
    const pingInterval = setInterval(() => {
      send({ action: 'ping' })
    }, 15000)

    return () => {
      clearInterval(pingInterval)
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect, send])

  return { connected, trades, defense, agents, positions, equity, consensus, send }
}
