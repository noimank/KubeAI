import axios, { type InternalAxiosRequestConfig } from 'axios'

import { useAuthStore } from '@/stores/authStore'
import { getMessageInstance } from '@/utils/messageHolder'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, API_BASE_URL } from '@/utils/constants'

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    _retry?: boolean
    _skipErrorHandler?: boolean
  }
}

function toCamelCase(str: string): string {
  return str.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
}

// 不递归转换其内部键名的白名单字段 —— 例如 env_vars 的值是以用户自定义
// 环境变量名为 key 的 dict，不应被驼峰/下划线风格转换。
const SKIP_RECURSE_KEYS = new Set(['env_vars', 'envVars'])

function toSnakeCase(str: string): string {
  return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)
}

function transformKeys<T>(
  obj: T,
  transformer: (key: string) => string,
  skipRecurseKeys?: Set<string>,
): T {
  if (obj === null || obj === undefined) return obj
  if (obj instanceof FormData || obj instanceof File || obj instanceof Blob) return obj
  if (Array.isArray(obj))
    return obj.map((item) => transformKeys(item, transformer, skipRecurseKeys)) as T
  if (typeof obj === 'object' && obj.constructor === Object) {
    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(obj)) {
      const newKey = transformer(key)
      // 白名单字段的值原样透传，不递归转换其内部键名
      // 例如 env_vars 的 key 是用户自定义环境变量名，不应被驼峰/下划线转换
      result[newKey] =
        skipRecurseKeys?.has(key) || skipRecurseKeys?.has(newKey)
          ? value
          : transformKeys(value, transformer, skipRecurseKeys)
    }
    return result as T
  }
  return obj
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (config.data && !(config.data instanceof FormData)) {
    config.data = transformKeys(config.data, toSnakeCase, SKIP_RECURSE_KEYS)
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  if (config.params) {
    config.params = transformKeys(config.params, toSnakeCase, SKIP_RECURSE_KEYS)
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    response.data = transformKeys(response.data, toCamelCase, SKIP_RECURSE_KEYS)
    return response
  },
  (error) => {
    if (!error.response) {
      getMessageInstance()?.error('网络错误，请检查网络连接')
      return Promise.reject(error)
    }

    const { status, data } = error.response
    const errorMessage = data?.message || ''
    const originalRequest = error.config

    if (originalRequest?._skipErrorHandler) {
      return Promise.reject(error)
    }

    if (status === 401 && !originalRequest._retry) {
      if (originalRequest.url?.includes('/auth/refresh')) {
        const authStore = useAuthStore.getState()
        authStore.logout()
        getMessageInstance()?.warning('会话已过期，请重新登录')
        window.location.href = '/login'
        return Promise.reject(error)
      }

      return handleTokenRefresh(originalRequest)
    }

    switch (status) {
      case 403:
        getMessageInstance()?.error('权限不足')
        break
      default:
        if (status >= 400 && status < 500) {
          getMessageInstance()?.error(errorMessage || '请求错误')
        } else if (status >= 500) {
          getMessageInstance()?.error('服务器错误，请稍后重试')
        }
    }

    return Promise.reject(error)
  },
)

let isRefreshing = false
let refreshSubscribers: Array<(token: string | null) => void> = []

function publishRefreshedToken(token: string | null) {
  refreshSubscribers.forEach((cb) => cb(token))
  refreshSubscribers = []
}

/**
 * Shared access-token refresh primitive.
 *
 * Concurrent callers share a single in-flight refresh: the first one performs
 * the refresh, the rest queue and receive the same result. Returns the new
 * access token, or null when refresh fails (the user is logged out and
 * redirected in that case). Used both by the axios 401 interceptor and by the
 * SSE log stream (which is read via fetch, since EventSource cannot carry an
 * Authorization header).
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (isRefreshing) {
    return new Promise((resolve) => {
      refreshSubscribers.push(resolve)
    })
  }

  isRefreshing = true
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!refreshToken) {
    publishRefreshedToken(null)
    isRefreshing = false
    const authStore = useAuthStore.getState()
    authStore.logout()
    window.location.href = '/login'
    return null
  }

  try {
    const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, {
      refresh_token: refreshToken,
    })

    const responseData = data?.data || data
    const newAccessToken = responseData.access_token
    const newRefreshToken = responseData.refresh_token

    localStorage.setItem(ACCESS_TOKEN_KEY, newAccessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, newRefreshToken)

    const authStore = useAuthStore.getState()
    authStore.setTokens(newAccessToken, newRefreshToken)

    publishRefreshedToken(newAccessToken)
    return newAccessToken
  } catch {
    publishRefreshedToken(null)
    const authStore = useAuthStore.getState()
    authStore.logout()
    getMessageInstance()?.warning('会话已过期，请重新登录')
    window.location.href = '/login'
    return null
  } finally {
    isRefreshing = false
  }
}

async function handleTokenRefresh(originalRequest: InternalAxiosRequestConfig) {
  originalRequest._retry = true
  const newAccessToken = await refreshAccessToken()
  if (!newAccessToken) {
    return Promise.reject(originalRequest)
  }
  originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
  return api(originalRequest)
}

export { api, transformKeys, toCamelCase, toSnakeCase }
