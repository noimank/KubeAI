import { useEffect, useRef, useCallback } from 'react'

interface UseWebSocketOptions {
  url: string | null
  onMessage: (data: unknown) => void
  enabled?: boolean
  reconnectInterval?: number
  maxRetries?: number
}

export function useWebSocket({
  url,
  onMessage,
  enabled = true,
  reconnectInterval = 5000,
  maxRetries = 3,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  const connect = useCallback(() => {
    if (!url || !enabled) return

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        retriesRef.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessageRef.current(data)
        } catch {
          // ignore non-JSON messages
        }
      }

      ws.onclose = () => {
        if (retriesRef.current < maxRetries) {
          retriesRef.current++
          timerRef.current = setTimeout(connect, reconnectInterval)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      // WebSocket constructor may throw in unsupported environments
    }
  }, [url, enabled, maxRetries, reconnectInterval])

  useEffect(() => {
    connect()
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  return wsRef
}
