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
