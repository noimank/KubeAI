export interface BaseResponse<T> {
  success: boolean
  message: string
  data: T | null
}

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export type PageResponse<T> = BaseResponse<PageData<T>>
