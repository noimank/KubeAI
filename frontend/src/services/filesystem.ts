import type { BaseResponse } from '@/types/api'

import { api } from './api'

export type FsEntryType = 'directory' | 'file'

export interface FsEntry {
  name: string
  path: string
  type: FsEntryType
  sizeBytes?: number
}

export interface FsBrowseResponse {
  path: string
  entries: FsEntry[]
  truncated: boolean
}

export async function browseFilesystem(path: string): Promise<FsBrowseResponse> {
  const res = await api.get<BaseResponse<FsBrowseResponse>>('/filesystem/browse', {
    params: { path },
  })
  return res.data.data!
}
