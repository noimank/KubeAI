/**
 * 全局常量 —— 项目中所有魔法字符串/数字的单一来处。
 * 禁止在 store / service / page 中重复定义这些常量。
 */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api'

export const ACCESS_TOKEN_KEY = 'kubeai_access_token'
export const REFRESH_TOKEN_KEY = 'kubeai_refresh_token'
export const THEME_KEY = 'kubeai_theme'

/** 分页默认条数（列表页可按需覆盖为 20） */
export const DEFAULT_PAGE_SIZE = 10

/** 文件上传上限：5 GiB */
export const MAX_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024

/**
 * 构建同源 WebSocket URL。
 * 强制使用当前页面 origin(ws/wss 随页面协议自适应), API_BASE_URL 仅作为路径前缀 ——
 * 后端主机/端口一律经反向代理(nginx / APISIX / vite proxy)同源转发, 不进浏览器 URL。
 */
export function buildWsUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}${API_BASE_URL}${path}`
}
