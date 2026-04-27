import axios from 'axios'
import { message } from 'antd'

const ACCESS_TOKEN_KEY = 'kubeai_access_token'

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
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
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
  if (config.params) {
    config.params = transformKeys(config.params, toSnakeCase)
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    const data = transformKeys(response.data, toCamelCase)
    if (data && typeof data === 'object' && 'success' in data && 'data' in data) {
      response.data = data
    } else {
      response.data = data
    }
    return response
  },
  (error) => {
    if (!error.response) {
      message.error('网络错误，请检查网络连接')
      return Promise.reject(error)
    }

    const { status, data } = error.response
    const errorMessage = data?.message || ''

    switch (status) {
      case 401:
        localStorage.removeItem(ACCESS_TOKEN_KEY)
        window.location.href = '/login'
        break
      case 403:
        message.error('权限不足')
        break
      default:
        if (status >= 400 && status < 500) {
          message.error(errorMessage || '请求错误')
        } else if (status >= 500) {
          message.error('服务器错误，请稍后重试')
        }
    }

    return Promise.reject(error)
  },
)

export { api, transformKeys, toCamelCase, toSnakeCase }
export { ACCESS_TOKEN_KEY }
