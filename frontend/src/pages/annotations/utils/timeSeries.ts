export interface ParsedTimeSeries {
  /** X 轴值：时间戳(ms)、数值或行索引 */
  times: number[]
  channels: { column: string; values: number[] }[]
}

/** 解析单个时间值为数值：优先数值，其次 Date.parse，最后 NaN（调用方可回退行索引） */
function toTimeValue(raw: string): number {
  const trimmed = raw.trim()
  const num = Number(trimmed)
  if (!Number.isNaN(num) && trimmed !== '') return num
  const parsed = Date.parse(trimmed)
  return Number.isNaN(parsed) ? NaN : parsed
}

/**
 * 解析 TimeSeries CSV 文本 → {times, channels}。
 * timeColumn 指定时间列；其余列作为通道。sep 默认逗号。
 */
export function parseTimeSeriesCSV(
  csv: string,
  opts: { sep?: string; timeColumn?: string } = {},
): ParsedTimeSeries | null {
  const sep = opts.sep ?? ','
  const lines = csv
    .trim()
    .split(/\r?\n/)
    .filter((l) => l.trim())
  if (lines.length < 2) return null
  const headers = lines[0].split(sep).map((h) => h.trim())
  const rows = lines.slice(1).map((l) => l.split(sep))
  const timeIdx = opts.timeColumn ? headers.indexOf(opts.timeColumn) : -1

  let times: number[]
  if (timeIdx >= 0) {
    times = rows.map((r) => {
      const v = toTimeValue(r[timeIdx] ?? '')
      return Number.isNaN(v) ? NaN : v
    })
    // 若整列无法解析，回退为行索引
    if (times.every((t) => Number.isNaN(t))) {
      times = rows.map((_, i) => i)
    } else {
      times = times.map((t) => (Number.isNaN(t) ? 0 : t))
    }
  } else {
    times = rows.map((_, i) => i)
  }

  const channels = headers
    .map((column, idx) => ({ column, idx }))
    .filter((c) => c.idx !== timeIdx)
    .map((c) => ({
      column: c.column,
      values: rows.map((r) => {
        const n = Number((r[c.idx] ?? '').trim())
        return Number.isNaN(n) ? 0 : n
      }),
    }))

  return { times, channels }
}

/**
 * 解析 JSON 数据（对象数组或 {column: number[]}）。
 */
export function parseTimeSeriesJSON(
  value: unknown,
  opts: { timeColumn?: string } = {},
): ParsedTimeSeries | null {
  if (!Array.isArray(value) || value.length === 0) return null
  if (typeof value[0] === 'object' && value[0] !== null) {
    const rows = value as Record<string, unknown>[]
    const keys = Object.keys(rows[0])
    const timeKey = opts.timeColumn && keys.includes(opts.timeColumn) ? opts.timeColumn : keys[0]
    const times = rows.map((r) => {
      const raw = r[timeKey]
      if (typeof raw === 'number') return raw
      if (typeof raw === 'string') {
        const v = toTimeValue(raw)
        return Number.isNaN(v) ? 0 : v
      }
      return 0
    })
    const channels = keys
      .filter((k) => k !== timeKey)
      .map((column) => ({
        column,
        values: rows.map((r) => {
          const n = Number(r[column])
          return Number.isNaN(n) ? 0 : n
        }),
      }))
    return { times, channels }
  }
  return null
}

/** 解析任意 TimeSeries 数据源（CSV 字符串 / JSON / URL 字符串） */
export function parseTimeSeriesData(
  raw: unknown,
  opts: { sep?: string; timeColumn?: string } = {},
): ParsedTimeSeries | null {
  if (raw == null) return null
  if (typeof raw === 'string') {
    const trimmed = raw.trim()
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        return parseTimeSeriesJSON(JSON.parse(trimmed), opts)
      } catch {
        /* fallthrough to CSV */
      }
    }
    return parseTimeSeriesCSV(raw, opts)
  }
  return parseTimeSeriesJSON(raw, opts)
}

/** 判断字符串是否为需 fetch 的 URL */
export function isUrlValue(value: unknown): boolean {
  return typeof value === 'string' && /^(https?:\/)?\//.test(value.trim())
}

/** 从 URL 加载文本（注入鉴权 token） */
export async function fetchTimeSeriesText(url: string): Promise<string> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`加载时间序列失败: ${res.status}`)
  return res.text()
}
