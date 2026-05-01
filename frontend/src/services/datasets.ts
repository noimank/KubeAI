import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  Dataset,
  DatasetDetail,
  DatasetMountInfo,
  DatasetVersion,
  VersionFile,
  VersionStats,
} from '@/types/dataset'

export async function getDatasets(params: {
  current: number
  pageSize: number
  keyword?: string
  startDate?: string
  endDate?: string
}): Promise<PageData<Dataset>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<Dataset>>>('/datasets', {
    params: { page: current, pageSize, ...rest },
  })
  return res.data.data!
}

export async function getDatasetDetail(id: string): Promise<BaseResponse<DatasetDetail>> {
  const res = await api.get<BaseResponse<DatasetDetail>>(`/datasets/${id}`)
  return res.data
}

export async function deleteDataset(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/datasets/${id}`)
  return res.data
}

export async function createDatasetVersion(
  datasetId: string,
  description?: string,
): Promise<DatasetVersion> {
  const res = await api.post<BaseResponse<DatasetVersion>>(`/datasets/${datasetId}/versions`, {
    description,
  })
  return res.data.data!
}

export async function deleteDatasetVersion(
  datasetId: string,
  versionId: string,
): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/datasets/${datasetId}/versions/${versionId}`)
  return res.data
}

export async function uploadVersionFiles(
  datasetId: string,
  versionId: string,
  files: File[],
): Promise<BaseResponse<unknown>> {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  const res = await api.post<BaseResponse<unknown>>(
    `/datasets/${datasetId}/versions/${versionId}/upload`,
    formData,
  )
  return res.data
}

export async function getVersionFiles(
  datasetId: string,
  versionId: string,
): Promise<VersionFile[]> {
  const res = await api.get<BaseResponse<VersionFile[]>>(
    `/datasets/${datasetId}/versions/${versionId}/files`,
  )
  return res.data.data!
}

export async function getVersionStats(datasetId: string, versionId: string): Promise<VersionStats> {
  const res = await api.get<BaseResponse<VersionStats>>(
    `/datasets/${datasetId}/versions/${versionId}/stats`,
  )
  return res.data.data!
}

export async function getFileDownloadUrl(
  datasetId: string,
  versionId: string,
  fileName: string,
): Promise<string> {
  const res = await api.post<BaseResponse<string>>(
    `/datasets/${datasetId}/versions/${versionId}/files/download-url`,
    { fileName },
  )
  return res.data.data!
}

export async function mountDatasetVersion(
  datasetId: string,
  versionId: string,
): Promise<DatasetMountInfo> {
  const res = await api.post<BaseResponse<DatasetMountInfo>>(
    `/datasets/${datasetId}/versions/${versionId}/mount`,
  )
  return res.data.data!
}

export async function getDatasetMountInfo(
  datasetId: string,
  versionId: string,
): Promise<DatasetMountInfo> {
  const res = await api.get<BaseResponse<DatasetMountInfo>>(
    `/datasets/${datasetId}/versions/${versionId}/mount`,
  )
  return res.data.data!
}

export async function unmountDatasetVersion(
  datasetId: string,
  versionId: string,
): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(
    `/datasets/${datasetId}/versions/${versionId}/mount`,
  )
  return res.data
}
