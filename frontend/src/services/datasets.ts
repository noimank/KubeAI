import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  Dataset,
  DatasetCreateParams,
  DatasetDetail,
  DatasetVersion,
  VersionFile,
  VersionStats,
} from '@/types/dataset'

export async function createDataset(params: DatasetCreateParams): Promise<DatasetDetail> {
  const res = await api.post<BaseResponse<DatasetDetail>>('/datasets', params)
  return res.data.data!
}

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

export async function getDatasetDetail(id: string): Promise<DatasetDetail> {
  const res = await api.get<BaseResponse<DatasetDetail>>(`/datasets/${id}`)
  return res.data.data!
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

export function getFileDownloadUrl(datasetId: string, versionId: string, fileName: string): string {
  return `/api/datasets/${datasetId}/versions/${versionId}/files/${encodeURIComponent(fileName)}/download`
}

export async function fetchFileBlob(
  datasetId: string,
  versionId: string,
  fileName: string,
): Promise<Blob> {
  const url = `/datasets/${datasetId}/versions/${versionId}/files/${encodeURIComponent(fileName)}/download`
  const res = await api.get(url, { responseType: 'blob' })
  return res.data as Blob
}

export function createBlobUrl(blob: Blob): string {
  return URL.createObjectURL(blob)
}

export function revokeBlobUrl(url: string): void {
  URL.revokeObjectURL(url)
}

export async function downloadFile(
  datasetId: string,
  versionId: string,
  fileName: string,
): Promise<void> {
  const blob = await fetchFileBlob(datasetId, versionId, fileName)
  const url = createBlobUrl(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  revokeBlobUrl(url)
}

export async function deleteVersionFile(
  datasetId: string,
  versionId: string,
  fileName: string,
): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(
    `/datasets/${datasetId}/versions/${versionId}/files/${encodeURIComponent(fileName)}`,
  )
  return res.data
}
