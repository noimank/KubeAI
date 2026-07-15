import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  AnnotationTemplate,
  AnnotationTemplateCreateRequest,
  AnnotationTemplateDetail,
  AnnotationTemplateImportItem,
  AnnotationTemplateUpdateRequest,
} from '@/types/annotation-template'

export async function listAnnotationTemplates(params: {
  current: number
  pageSize: number
  name?: string
  tag?: string
  group?: string
}): Promise<PageData<AnnotationTemplate>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<AnnotationTemplate>>>(
    '/annotation-templates',
    { params: { page: current, pageSize, ...rest } },
  )
  return res.data.data!
}

export async function getAnnotationTemplate(id: string): Promise<AnnotationTemplateDetail> {
  const res = await api.get<BaseResponse<AnnotationTemplateDetail>>(
    `/annotation-templates/${id}`,
  )
  return res.data.data!
}

export async function createAnnotationTemplate(
  data: AnnotationTemplateCreateRequest,
): Promise<AnnotationTemplateDetail> {
  const res = await api.post<BaseResponse<AnnotationTemplateDetail>>(
    '/annotation-templates',
    data,
  )
  return res.data.data!
}

export async function updateAnnotationTemplate(
  id: string,
  data: AnnotationTemplateUpdateRequest,
): Promise<AnnotationTemplate> {
  const res = await api.patch<BaseResponse<AnnotationTemplate>>(
    `/annotation-templates/${id}`,
    data,
  )
  return res.data.data!
}

export async function deleteAnnotationTemplate(id: string): Promise<void> {
  await api.delete<BaseResponse<null>>(`/annotation-templates/${id}`)
}

export async function listLsImportableTemplates(): Promise<AnnotationTemplateImportItem[]> {
  const res = await api.get<BaseResponse<AnnotationTemplateImportItem[]>>(
    '/annotation-templates/ls-imports',
  )
  return res.data.data!
}

export async function listAnnotationTemplateGroups(): Promise<string[]> {
  const res = await api.get<BaseResponse<string[]>>('/annotation-templates/groups')
  return res.data.data!
}
