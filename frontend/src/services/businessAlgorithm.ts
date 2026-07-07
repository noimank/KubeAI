import axios from 'axios'

import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/utils/constants'

/**
 * 业务算法库专用 axios 实例.
 *
 * 不经过全局 api 实例的 snake_case 转换, 直接透传 camelCase 字段名,
 * 以兼容 balibrary 的接口契约.
 */
const algorithmApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000,
  headers: { 'Content-Type': 'application/json' },
})

algorithmApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const optimizeHa = (data: any) =>
  algorithmApi.post('/algorithm_api/heuristicAlgorithms/optimize', data)

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const optimizeDp = (data: any) =>
  algorithmApi.post('/algorithm_api/dataPlanning/optimize', data)

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const optimizeHr = (data: any) =>
  algorithmApi.post('/algorithm_api/heuristicRules/optimize', data)
