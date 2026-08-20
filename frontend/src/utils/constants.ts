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
 * 为 KubeAI 内部 API URL 追加 JWT Token 查询参数。
 * 用于 <img> / <audio> / <video> 等无法携带 Authorization Header 的浏览器原生请求。
 *
 * @param url - KubeAI 内部 API URL（如 /api/datasets/.../download）
 * @returns 带 ?token= 查询参数的 URL；若未登录则原样返回
 */
export function appendAuthToken(url: string): string {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (!token) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}token=${encodeURIComponent(token)}`
}
