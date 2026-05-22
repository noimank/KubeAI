import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  DevEnvironmentImage,
  DevEnvironmentImageCreateParams,
  DevEnvironmentImageUpdateParams,
  DevEnvironmentImageSelectable,
} from '@/types/dev-environment-image'

export async function getDevEnvironmentImages(params: {
  current: number
  pageSize: number
  keyword?: string
  environmentType?: string
}): Promise<PageData<DevEnvironmentImage>> {
  const res = await api.get<BaseResponse<PageData<DevEnvironmentImage>>>(
    '/dev-environment-images',
    {
      params: {
        page: params.current,
        page_size: params.pageSize,
        keyword: params.keyword,
        environment_type: params.environmentType,
      },
    },
  )
  return res.data.data!
}

export async function getDevEnvironmentImage(id: string): Promise<DevEnvironmentImage> {
  const res = await api.get<BaseResponse<DevEnvironmentImage>>(`/dev-environment-images/${id}`)
  return res.data.data!
}

export async function createDevEnvironmentImage(
  data: DevEnvironmentImageCreateParams,
): Promise<DevEnvironmentImage> {
  const res = await api.post<BaseResponse<DevEnvironmentImage>>('/dev-environment-images', data)
  return res.data.data!
}

export async function updateDevEnvironmentImage(
  id: string,
  data: DevEnvironmentImageUpdateParams,
): Promise<DevEnvironmentImage> {
  const res = await api.put<BaseResponse<DevEnvironmentImage>>(
    `/dev-environment-images/${id}`,
    data,
  )
  return res.data.data!
}

export async function deleteDevEnvironmentImage(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/dev-environment-images/${id}`)
  return res.data
}

export async function toggleDevEnvironmentImage(id: string): Promise<DevEnvironmentImage> {
  const res = await api.patch<BaseResponse<DevEnvironmentImage>>(
    `/dev-environment-images/${id}/toggle`,
  )
  return res.data.data!
}

export async function getSelectableDevEnvironmentImages(): Promise<
  DevEnvironmentImageSelectable[]
> {
  const res = await api.get<BaseResponse<DevEnvironmentImageSelectable[]>>(
    '/dev-environment-images/selectable',
  )
  return res.data.data!
}
