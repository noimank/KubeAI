import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Input, Space, Spin } from 'antd'
import { SearchOutlined, DownOutlined } from '@ant-design/icons'

const ERROR_KEYWORDS = ['ERROR', 'FATAL', 'Exception', 'Traceback', 'FAILED', 'AssertionError']
const LINE_HEIGHT = 20
const BUFFER = 10
const MAX_LINES = 5000

interface LogStreamProps {
  streamUrl?: string | null
  initialLines?: string[]
  loading?: boolean
  streamable?: boolean
  maxLines?: number
  emptyText?: string
}

function isErrorLine(line: string): boolean {
  return ERROR_KEYWORDS.some((kw) => line.includes(kw))
}

export default function LogStream({
  streamUrl,
  initialLines,
  loading = false,
  streamable = false,
  maxLines = MAX_LINES,
  emptyText = '暂无日志',
}: LogStreamProps) {
  const [lines, setLines] = useState<string[]>(() => initialLines ?? [])
  const [autoScroll, setAutoScroll] = useState(true)
  const [searchText, setSearchText] = useState('')
  const [currentMatchIndex, setCurrentMatchIndex] = useState(-1)

  const containerRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  // SSE connection
  useEffect(() => {
    if (!streamable || !streamUrl) return

    const es = new EventSource(streamUrl)
    eventSourceRef.current = es

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.line) {
          setLines((prev) => {
            const next = [...prev, data.line]
            return next.length > maxLines ? next.slice(-maxLines) : next
          })
        }
      } catch {
        // ignore malformed events
      }
    }

    es.onerror = () => {
      // EventSource auto-reconnects
    }

    return () => {
      es.close()
      eventSourceRef.current = null
    }
  }, [streamUrl, streamable, maxLines])

  // Sync initialLines when not streaming
  useEffect(() => {
    if (!streamable && initialLines) {
      setLines(initialLines)
    }
  }, [initialLines, streamable])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [lines, autoScroll])

  // Search matches
  const matchIndices = useMemo(() => {
    if (!searchText) return []
    const lower = searchText.toLowerCase()
    return lines.reduce<number[]>((acc, line, i) => {
      if (line.toLowerCase().includes(lower)) acc.push(i)
      return acc
    }, [])
  }, [lines, searchText])

  const matchCount = matchIndices.length

  // Navigate matches
  const goToMatch = useCallback(
    (direction: 'next' | 'prev') => {
      if (!matchIndices.length) return
      setCurrentMatchIndex((prev) => {
        if (prev === -1) return 0
        const idx = matchIndices.indexOf(prev)
        if (idx === -1) return matchIndices[0]
        const next =
          direction === 'next'
            ? matchIndices[(idx + 1) % matchIndices.length]
            : matchIndices[(idx - 1 + matchIndices.length) % matchIndices.length]
        // Scroll to matched line
        if (scrollRef.current) {
          scrollRef.current.scrollTop = next * LINE_HEIGHT
        }
        return next
      })
    },
    [matchIndices],
  )

  // Scroll handler for auto-scroll detection
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setAutoScroll(distanceFromBottom < 50)
  }, [])

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      setAutoScroll(true)
    }
  }, [])

  // Virtual scrolling calculation
  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(0)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })
    observer.observe(el)
    setContainerHeight(el.clientHeight)
    return () => observer.disconnect()
  }, [])

  const visibleStartIndex = Math.max(0, Math.floor(scrollTop / LINE_HEIGHT) - BUFFER)
  const visibleEndIndex = Math.min(
    lines.length,
    Math.ceil((scrollTop + containerHeight) / LINE_HEIGHT) + BUFFER,
  )
  const visibleLines = lines.slice(visibleStartIndex, visibleEndIndex)

  const updateScrollTop = useCallback(() => {
    if (scrollRef.current) {
      setScrollTop(scrollRef.current.scrollTop)
    }
  }, [])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    )
  }

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
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
            setCurrentMatchIndex(-1)
          }}
          style={{ width: 240 }}
          allowClear
        />
        {searchText && (
          <Space size={4}>
            <span style={{ fontSize: 12, color: '#999' }}>
              {currentMatchIndex >= 0
                ? `${matchIndices.indexOf(currentMatchIndex) + 1}/${matchCount}`
                : `${matchCount} 条结果`}
            </span>
            <Button
              size="small"
              type="text"
              disabled={!matchCount}
              onClick={() => goToMatch('prev')}
            >
              ↑
            </Button>
            <Button
              size="small"
              type="text"
              disabled={!matchCount}
              onClick={() => goToMatch('next')}
            >
              ↓
            </Button>
          </Space>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 12, color: '#999' }}>{lines.length} 行</span>
      </div>

      {/* Log viewport */}
      <div
        ref={scrollRef}
        onScroll={() => {
          handleScroll()
          updateScrollTop()
        }}
        style={{
          flex: 1,
          overflow: 'auto',
          position: 'relative',
          background: '#fafafa',
          fontFamily: "'SF Mono', 'Fira Code', Consolas, monospace",
          fontSize: 13,
          lineHeight: `${LINE_HEIGHT}px`,
        }}
      >
        {lines.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>{emptyText}</div>
        ) : (
          <div style={{ height: lines.length * LINE_HEIGHT, position: 'relative' }}>
            {visibleLines.map((line, i) => {
              const globalIndex = visibleStartIndex + i
              const isError = isErrorLine(line)
              const isMatch = searchText && line.toLowerCase().includes(searchText.toLowerCase())
              const isCurrentMatch = globalIndex === currentMatchIndex

              let background = 'transparent'
              if (isCurrentMatch) background = '#ffc069'
              else if (isMatch) background = '#fff566'
              else if (isError) background = 'rgba(255,77,79,0.1)'

              return (
                <div
                  key={globalIndex}
                  style={{
                    position: 'absolute',
                    top: globalIndex * LINE_HEIGHT,
                    left: 0,
                    right: 0,
                    height: LINE_HEIGHT,
                    paddingLeft: 12,
                    paddingRight: 12,
                    whiteSpace: 'pre',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    background,
                  }}
                >
                  <span style={{ color: '#bbb', marginRight: 8, userSelect: 'none' }}>
                    {globalIndex + 1}
                  </span>
                  {line}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Scroll to bottom button */}
      {!autoScroll && lines.length > 0 && (
        <Button
          type="primary"
          shape="round"
          icon={<DownOutlined />}
          onClick={scrollToBottom}
          style={{
            position: 'absolute',
            bottom: 16,
            right: 24,
            zIndex: 10,
          }}
        >
          回到最新
        </Button>
      )}
    </div>
  )
}
