export interface BaseResponse<T> {
  success: boolean
  message: string
  data: T | null
}

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export type PageResponse<T> = BaseResponse<PageData<T>>
