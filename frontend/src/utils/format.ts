import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

export function formatDate(date: string | Date, format = 'YYYY-MM-DD HH:mm:ss'): string {
  return dayjs(date).format(format)
}

export function formatRelative(date: string | Date): string {
  return dayjs(date).fromNow()
}

export function formatNumber(num: number): string {
  if (num >= 1_000_000_000) return `${(num / 1_000_000_000).toFixed(1)}B`
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`
  return String(num)
}

export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

export function formatKi(ki: number): string {
  if (ki <= 0) return '0 Ki'
  if (ki >= 1024 ** 3) return `${(ki / 1024 ** 3).toFixed(1)} Ti`
  if (ki >= 1024 ** 2) return `${(ki / 1024 ** 2).toFixed(1)} Gi`
  if (ki >= 1024) return `${(ki / 1024).toFixed(1)} Mi`
  return `${Math.round(ki)} Ki`
}

export function parseK8sQuantity(val: string | number): number {
  if (typeof val === 'number') return val
  if (!val || val === '0') return 0
  const str = String(val)
  const num = parseFloat(str)
  if (str.endsWith('Ti')) return num * 1024 ** 3
  if (str.endsWith('Gi')) return num * 1024 ** 2
  if (str.endsWith('Mi')) return num * 1024
  if (str.endsWith('Ki')) return num
  if (str.endsWith('m')) return num / 1000
  return num
}

export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}
