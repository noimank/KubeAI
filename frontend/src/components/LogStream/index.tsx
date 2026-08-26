import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Input, Space, Spin } from 'antd'
import { SearchOutlined, DownOutlined, DownloadOutlined } from '@ant-design/icons'

const ERROR_KEYWORDS = ['ERROR', 'FATAL', 'Exception', 'Traceback', 'FAILED', 'AssertionError']
const MAX_LINES = 5000
const FOLLOW_THRESHOLD = 50 // px from bottom within which we keep auto-scrolling
// K8s pod logs with timestamps=True arrive as "<RFC3339 timestamp> <content>"
const TS_PATTERN = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s(.*)$/

interface LogStreamProps {
  streamUrl?: string | null
  initialLines?: string[]
  loading?: boolean
  streamable?: boolean
  maxLines?: number
  emptyText?: string
  downloadName?: string
}

interface ParsedLine {
  ts: string | null
  content: string
}

function isErrorLine(content: string): boolean {
  return ERROR_KEYWORDS.some((kw) => content.includes(kw))
}

function parseLine(line: string): ParsedLine {
  const m = TS_PATTERN.exec(line)
  return m ? { ts: m[1], content: m[2] } : { ts: null, content: line }
}

function formatTime(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function stamp(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    `-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  )
}

export default function LogStream({
  streamUrl,
  initialLines,
  loading = false,
  streamable = false,
  maxLines = MAX_LINES,
  emptyText = '暂无日志',
  downloadName = 'logs',
}: LogStreamProps) {
  const [lines, setLines] = useState<string[]>(() => initialLines ?? [])
  const [autoScroll, setAutoScroll] = useState(true)
  const [searchText, setSearchText] = useState('')
  const [matchPos, setMatchPos] = useState(0) // position within matchIndices

  const scrollRef = useRef<HTMLDivElement>(null)

  // 日志流走 WebSocket —— SSE 在双层 nginx(Tengine + APISIX)下会被 Tengine 缓冲,
  // 运行中日志攒在缓冲区, 任务结束 follow 流 EOF 才 flush; WebSocket 是升级连接,
  // nginx 直接透传。鉴权走同源 Cookie (kubeai_access_token), URL 不携带 token,
  // 重连时浏览器自动带最新 Cookie(兼容 token 刷新)。
  useEffect(() => {
    if (!streamable || !streamUrl) return

    let stopped = false // unmount / dependency change → permanent stop
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let pingTimer: ReturnType<typeof setInterval> | undefined
    let backoffMs = 1000
    const BACKOFF_MAX = 15000
    const PING_INTERVAL_MS = 25000 // half-open 检测: 定期 ping, 链路死亡时 onclose 触发重连

    function appendLine(line: string) {
      setLines((prev) => {
        const next = [...prev, line]
        return next.length > maxLines ? next.slice(-maxLines) : next
      })
    }

    function scheduleReconnect() {
      if (stopped) return
      reconnectTimer = setTimeout(connect, backoffMs)
      backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX)
    }

    function connect() {
      if (stopped || !streamUrl) return
      ws = new WebSocket(streamUrl)
      ws.onopen = () => {
        backoffMs = 1000 // 连接健康, 重置退避
        pingTimer = setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) ws.send('ping')
        }, PING_INTERVAL_MS)
      }
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as { line?: string; error?: string }
          if (data.line) appendLine(data.line)
          // pong / error 帧静默(error 为任务不存在等终态, 由 onclose 重连)
        } catch {
          /* 忽略非 JSON 帧 */
        }
      }
      ws.onclose = () => {
        if (pingTimer) clearInterval(pingTimer)
        if (!stopped) scheduleReconnect()
      }
      ws.onerror = () => {
        try {
          ws?.close()
        } catch {
          /* 忽略 */
        }
      }
    }

    void connect()

    return () => {
      stopped = true
      if (pingTimer) clearInterval(pingTimer)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      try {
        ws?.close()
      } catch {
        /* 忽略 */
      }
    }
  }, [streamUrl, streamable, maxLines])

  // Snapshot sync (history mode)
  useEffect(() => {
    if (!streamable && initialLines) {
      setLines(initialLines)
    }
  }, [initialLines, streamable])

  // Auto-scroll to the latest line
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lines, autoScroll])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setAutoScroll(distanceFromBottom < FOLLOW_THRESHOLD)
  }, [])

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    setAutoScroll(true)
  }, [])

  // Split the K8s timestamp prefix out so we can render/search content only
  const parsedLines = useMemo(() => lines.map(parseLine), [lines])

  // Match indices for current search (over content, not the timestamp prefix)
  const matchIndices = useMemo(() => {
    if (!searchText) return []
    const needle = searchText.toLowerCase()
    return parsedLines.reduce<number[]>((acc, { content }, i) => {
      if (content.toLowerCase().includes(needle)) acc.push(i)
      return acc
    }, [])
  }, [parsedLines, searchText])

  const matchCount = matchIndices.length
  const safePos = matchCount ? matchPos % matchCount : 0
  const currentLineIdx = matchCount ? matchIndices[safePos] : -1

  // Bring the active match into view
  useEffect(() => {
    if (currentLineIdx < 0) return
    scrollRef.current
      ?.querySelector<HTMLElement>(`[data-idx="${currentLineIdx}"]`)
      ?.scrollIntoView({ block: 'center' })
  }, [currentLineIdx])

  const jumpToMatch = useCallback(
    (direction: 'next' | 'prev') => {
      if (!matchCount) return
      setMatchPos((p) =>
        direction === 'next' ? (p + 1) % matchCount : (p - 1 + matchCount) % matchCount,
      )
    },
    [matchCount],
  )

  const handleDownload = useCallback(() => {
    if (!lines.length) return
    // Export the raw lines (timestamps preserved) for offline analysis
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${downloadName}-${stamp()}.log`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }, [lines, downloadName])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 12px',
          borderBottom: '1px solid #f0f0f0',
          flexShrink: 0,
        }}
      >
        <Input
          size="small"
          placeholder="搜索日志..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => {
            setSearchText(e.target.value)
            setMatchPos(0)
          }}
          style={{ width: 240 }}
          allowClear
        />
        {searchText && (
          <Space size={4}>
            <span style={{ fontSize: 12, color: '#999' }}>
              {matchCount ? `${safePos + 1}/${matchCount}` : '无匹配'}
            </span>
            <Button
              size="small"
              type="text"
              disabled={!matchCount}
              onClick={() => jumpToMatch('prev')}
            >
              ↑
            </Button>
            <Button
              size="small"
              type="text"
              disabled={!matchCount}
              onClick={() => jumpToMatch('next')}
            >
              ↓
            </Button>
          </Space>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: '#999' }}>{lines.length} 行</span>
        <Button
          size="small"
          type="text"
          icon={<DownloadOutlined />}
          disabled={!lines.length}
          onClick={handleDownload}
        >
          下载
        </Button>
      </div>

      {/* Log viewport */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'auto',
          background: '#fafafa',
          fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
          fontSize: 13,
          lineHeight: '20px',
        }}
      >
        {lines.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>{emptyText}</div>
        ) : (
          parsedLines.map((line, i) => {
            const isError = isErrorLine(line.content)
            const isMatch =
              !!searchText && line.content.toLowerCase().includes(searchText.toLowerCase())
            const isCurrent = i === currentLineIdx

            let background = 'transparent'
            if (isCurrent) background = '#ffc069'
            else if (isMatch) background = '#fff566'
            else if (isError) background = 'rgba(255,77,79,0.1)'

            return (
              <div
                key={i}
                data-idx={i}
                style={{ display: 'flex', padding: '0 12px', whiteSpace: 'pre-wrap', background }}
              >
                <span style={{ color: '#bbb', marginRight: 8, userSelect: 'none', flexShrink: 0 }}>
                  {i + 1}
                </span>
                {line.ts && (
                  <span
                    style={{ color: '#bbb', marginRight: 8, userSelect: 'none', flexShrink: 0 }}
                  >
                    {formatTime(line.ts)}
                  </span>
                )}
                <span style={{ flex: 1, wordBreak: 'break-word' }}>{line.content}</span>
              </div>
            )
          })
        )}
      </div>

      {/* Back to latest */}
      {!autoScroll && lines.length > 0 && (
        <Button
          type="primary"
          shape="round"
          icon={<DownOutlined />}
          onClick={scrollToBottom}
          style={{ position: 'absolute', bottom: 16, right: 24, zIndex: 10 }}
        >
          回到最新
        </Button>
      )}
    </div>
  )
}
