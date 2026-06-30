import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  Image,
  ImageBuildLog,
  ImageBuildParams,
  ImageCategory,
  ImageCreateParams,
  ImageSelectable,
  ImageUpdateParams,
} from '@/types/image'

export async function getImages(params: {
  current: number
  pageSize: number
  keyword?: string
  source?: string
  category?: ImageCategory
}): Promise<PageData<Image>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<Image>>>('/images', {
    params: { page: current, pageSize, ...rest },
  })
  return res.data.data!
}

export async function getImage(id: string): Promise<Image> {
  const res = await api.get<BaseResponse<Image>>(`/images/${id}`)
  return res.data.data!
}

export async function createImage(data: ImageCreateParams): Promise<Image> {
  const res = await api.post<BaseResponse<Image>>('/images', data)
  return res.data.data!
}

export async function updateImage(id: string, data: ImageUpdateParams): Promise<Image> {
  const res = await api.put<BaseResponse<Image>>(`/images/${id}`, data)
  return res.data.data!
}

export async function deleteImage(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/images/${id}`)
  return res.data
}

export async function toggleImage(id: string): Promise<Image> {
  const res = await api.patch<BaseResponse<Image>>(`/images/${id}/toggle`)
  return res.data.data!
}

export async function buildImage(data: ImageBuildParams): Promise<Image> {
  const res = await api.post<BaseResponse<Image>>('/images/build', data)
  return res.data.data!
}

export async function getBuildLog(id: string): Promise<ImageBuildLog> {
  const res = await api.get<BaseResponse<ImageBuildLog>>(`/images/${id}/build-log`)
  return res.data.data!
}

export async function rebuildImage(id: string): Promise<Image> {
  const res = await api.post<BaseResponse<Image>>(`/images/${id}/rebuild`)
  return res.data.data!
}

export async function getSelectableImages(category?: ImageCategory): Promise<ImageSelectable[]> {
  const res = await api.get<BaseResponse<ImageSelectable[]>>('/images/selectable', {
    params: category ? { category } : undefined,
  })
  return res.data.data!
}
