import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  AnnotationBatchAssignRequest,
  AnnotationProject,
  AnnotationProjectCreateRequest,
  AnnotationProjectDetail,
  AnnotationSubmitRequest,
  AnnotationTask,
  AnnotationTaskAssignRequest,
  AnnotationTaskSummary,
  AnnotationTaskUnassignRequest,
} from '@/types/annotation'

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

export async function getAnnotationProjectTasks(
  projectId: string,
  params: { current: number; pageSize: number; status?: string; assignedTo?: string },
): Promise<PageData<AnnotationTask>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<AnnotationTask>>>(
    `/annotations/projects/${projectId}/tasks`,
    { params: { page: current, pageSize, ...rest } },
  )
  return res.data.data!
}

export async function assignAnnotationTasks(
  projectId: string,
  data: AnnotationTaskAssignRequest,
): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>(`/annotations/projects/${projectId}/assign`, data)
  return res.data
}

export async function unassignAnnotationTasks(
  projectId: string,
  data: AnnotationTaskUnassignRequest,
): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>(
    `/annotations/projects/${projectId}/unassign`,
    data,
  )
  return res.data
}

export async function batchAssignAnnotationTasks(
  projectId: string,
  data: AnnotationBatchAssignRequest,
): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>(
    `/annotations/projects/${projectId}/batch-assign`,
    data,
  )
  return res.data
}

export async function getMyAnnotationTasks(params: {
  current: number
  pageSize: number
}): Promise<PageData<AnnotationTask>> {
  const { current, pageSize } = params
  const res = await api.get<BaseResponse<PageData<AnnotationTask>>>('/annotations/my-tasks', {
    params: { page: current, pageSize },
  })
  return res.data.data!
}

export async function getMyAnnotationTaskSummary(): Promise<AnnotationTaskSummary[]> {
  const res = await api.get<BaseResponse<AnnotationTaskSummary[]>>('/annotations/my-tasks/summary')
  return res.data.data!
}

export async function startAnnotation(taskId: string): Promise<AnnotationTask> {
  const res = await api.post<BaseResponse<AnnotationTask>>(`/annotations/tasks/${taskId}/start`)
  return res.data.data!
}

export async function submitAnnotation(
  taskId: string,
  data: AnnotationSubmitRequest,
): Promise<AnnotationTask> {
  const res = await api.post<BaseResponse<AnnotationTask>>(
    `/annotations/tasks/${taskId}/submit`,
    data,
  )
  return res.data.data!
}

export async function getNextAnnotationTask(projectId: string): Promise<AnnotationTask | null> {
  const res = await api.get<BaseResponse<AnnotationTask | null>>(
    `/annotations/projects/${projectId}/next-task`,
  )
  return res.data.data ?? null
}

export async function getMyProjectTaskIds(projectId: string): Promise<string[]> {
  const res = await api.get<BaseResponse<string[]>>(
    `/annotations/projects/${projectId}/my-task-ids`,
  )
  return res.data.data ?? []
}

export async function getAnnotationTaskDetail(taskId: string): Promise<AnnotationTask> {
  const res = await api.get<BaseResponse<AnnotationTask>>(`/annotations/tasks/${taskId}`)
  return res.data.data!
}

export async function cancelAnnotation(taskId: string): Promise<AnnotationTask> {
  const res = await api.post<BaseResponse<AnnotationTask>>(`/annotations/tasks/${taskId}/cancel`)
  return res.data.data!
}

export async function syncAnnotationProjectTasks(
  projectId: string,
): Promise<BaseResponse<{ syncedCount: number }>> {
  const res = await api.post<BaseResponse<{ syncedCount: number }>>(
    `/annotations/projects/${projectId}/sync-tasks`,
  )
  return res.data
}

export async function retryAnnotationProject(projectId: string): Promise<AnnotationProjectDetail> {
  const res = await api.post<BaseResponse<AnnotationProjectDetail>>(
    `/annotations/projects/${projectId}/retry`,
  )
  return res.data.data!
}
