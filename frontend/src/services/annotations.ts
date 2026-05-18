import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  AnnotationProject,
  AnnotationProjectCreateRequest,
  AnnotationProjectDetail,
  AnnotationTemplate,
} from '@/types/annotation'

export async function getAnnotationTemplates(): Promise<AnnotationTemplate[]> {
  const res = await api.get<BaseResponse<AnnotationTemplate[]>>('/annotations/templates')
  return res.data.data!
}

export async function createAnnotationProject(
  data: AnnotationProjectCreateRequest,
): Promise<AnnotationProjectDetail> {
  const res = await api.post<BaseResponse<AnnotationProjectDetail>>('/annotations/projects', data)
  return res.data.data!
}

export async function getAnnotationProjects(params: {
  current: number
  pageSize: number
  keyword?: string
}): Promise<PageData<AnnotationProject>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<AnnotationProject>>>('/annotations/projects', {
    params: { page: current, pageSize, ...rest },
  })
  return res.data.data!
}

export async function getAnnotationProjectDetail(id: string): Promise<AnnotationProjectDetail> {
  const res = await api.get<BaseResponse<AnnotationProjectDetail>>(`/annotations/projects/${id}`)
  return res.data.data!
}

export async function deleteAnnotationProject(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/annotations/projects/${id}`)
  return res.data
}
