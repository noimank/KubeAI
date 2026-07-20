import type { ColumnsType } from 'antd/es/table'

/** 将表格数据（JSON 对象数组 / CSV 字符串 / 二维数组）解析为列 + 行 */
export function toTableData(
  value: unknown,
  sep: string,
): { columns: ColumnsType<Record<string, unknown>>; rows: Record<string, unknown>[] } {
  // JSON 对象数组（排除二维数组 —— 数组也是 object）
  if (
    Array.isArray(value) &&
    value.length > 0 &&
    typeof value[0] === 'object' &&
    value[0] !== null &&
    !Array.isArray(value[0])
  ) {
    const keys = Array.from(new Set(value.flatMap((r) => Object.keys(r as object))))
    const columns: ColumnsType<Record<string, unknown>> = keys.map((k) => ({
      title: k,
      dataIndex: k,
      key: k,
    }))
    const rows = value as Record<string, unknown>[]
    return { columns, rows }
  }

  // CSV 字符串
  if (typeof value === 'string') {
    const lines = value.split(/\r?\n/).filter((l) => l.trim())
    if (lines.length < 2) return { columns: [], rows: [] }
    const split = (line: string) => line.split(sep).map((c) => c.trim())
    const headers = split(lines[0])
    const columns: ColumnsType<Record<string, unknown>> = headers.map((h) => ({
      title: h,
      dataIndex: h,
      key: h,
    }))
    const rows = lines.slice(1).map((line) => {
      const cells = split(line)
      const row: Record<string, unknown> = {}
      headers.forEach((h, i) => (row[h] = cells[i] ?? ''))
      return row
    })
    return { columns, rows }
  }

  // JSON 二维数组
  if (Array.isArray(value) && value.length > 1 && Array.isArray(value[0])) {
    const matrix = value as unknown[][]
    const headers = matrix[0].map(String)
    const columns: ColumnsType<Record<string, unknown>> = headers.map((h, i) => ({
      title: h,
      dataIndex: `col${i}`,
      key: `col${i}`,
    }))
    const rows = matrix.slice(1).map((cells) => {
      const row: Record<string, unknown> = {}
      headers.forEach((_, i) => (row[`col${i}`] = cells[i] ?? ''))
      return row
    })
    return { columns, rows }
  }

  return { columns: [], rows: [] }
}
