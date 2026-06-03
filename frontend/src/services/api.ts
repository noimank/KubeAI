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

function toSnakeCase(str: string): string {
  return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`)
}

function transformKeys<T>(obj: T, transformer: (key: string) => string): T {
  if (obj === null || obj === undefined) return obj
  if (obj instanceof FormData || obj instanceof File || obj instanceof Blob) return obj
  if (Array.isArray(obj)) return obj.map((item) => transformKeys(item, transformer)) as T
  if (typeof obj === 'object' && obj.constructor === Object) {
    const result: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(obj)) {
      result[transformer(key)] = transformKeys(value, transformer)
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
    config.data = transformKeys(config.data, toSnakeCase)
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  if (config.params) {
    config.params = transformKeys(config.params, toSnakeCase)
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    response.data = transformKeys(response.data, toCamelCase)
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
let refreshSubscribers: Array<(token: string) => void> = []

function onTokenRefreshed(newToken: string) {
  refreshSubscribers.forEach((cb) => cb(newToken))
  refreshSubscribers = []
}

function addRefreshSubscriber(callback: (token: string) => void) {
  refreshSubscribers.push(callback)
}

async function handleTokenRefresh(originalRequest: InternalAxiosRequestConfig) {
  if (isRefreshing) {
    return new Promise((resolve) => {
      addRefreshSubscriber((token: string) => {
        originalRequest.headers.Authorization = `Bearer ${token}`
        resolve(api(originalRequest))
      })
    })
  }

  originalRequest._retry = true
  isRefreshing = true

  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!refreshToken) {
    const authStore = useAuthStore.getState()
    authStore.logout()
    window.location.href = '/login'
    return Promise.reject(originalRequest)
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

    onTokenRefreshed(newAccessToken)

    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
    return api(originalRequest)
  } catch (refreshError) {
    refreshSubscribers = []
    const authStore = useAuthStore.getState()
    authStore.logout()
    getMessageInstance()?.warning('会话已过期，请重新登录')
    window.location.href = '/login'
    return Promise.reject(refreshError)
  } finally {
    isRefreshing = false
  }
}

export { api, transformKeys, toCamelCase, toSnakeCase }
