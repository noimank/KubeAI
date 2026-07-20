import { useCallback, useEffect, useState } from 'react'
import type { AnnotationTask } from '@/types/annotation'
import {
  getAnnotationTaskDetail,
  getMyProjectTaskIds,
  getNextAnnotationTask,
} from '@/services/annotations'
import { getMessageInstance } from '@/utils/messageHolder'

/**
 * 标注任务生命周期：任务列表加载、当前任务、光标、上下导航、全局方向键热键。
 *
 * globalResults 的重置由调用方通过监听 currentTask?.id 变化的 effect 处理，
 * 保持本 hook 单一职责（任务流转）。
 */
export interface UseAnnotationTaskReturn {
  taskIds: string[]
  cursor: number
  currentTask: AnnotationTask | null
  readOnly: boolean
  taskLoading: boolean
  taskLoadFailed: boolean
  initialized: boolean
  loadTaskById: (tid: string) => Promise<void>
  goPrev: () => Promise<void>
  goNext: () => Promise<void>
  /** 重新标注流：刷新当前任务并更新只读态 */
  refreshCurrentTask: () => Promise<void>
  setCurrentTask: (task: AnnotationTask | null) => void
  setReadOnly: (readOnly: boolean) => void
}

export function useAnnotationTask(projectId: string | undefined): UseAnnotationTaskReturn {
  const [taskIds, setTaskIds] = useState<string[]>([])
  const [cursor, setCursor] = useState(0)
  const [currentTask, setCurrentTask] = useState<AnnotationTask | null>(null)
  const [readOnly, setReadOnly] = useState(false)
  const [taskLoading, setTaskLoading] = useState(false)
  const [taskLoadFailed, setTaskLoadFailed] = useState(false)
  const [initialized, setInitialized] = useState(false)

  const loadTaskById = useCallback(
    async (tid: string) => {
      if (!projectId) return
      setTaskLoading(true)
      setTaskLoadFailed(false)
      try {
        const detail = await getAnnotationTaskDetail(tid)
        setCurrentTask(detail)
        setReadOnly(detail.status === 'completed')
      } catch {
        setTaskLoadFailed(true)
        getMessageInstance()?.error('加载任务失败')
      } finally {
        setTaskLoading(false)
      }
    },
    [projectId],
  )

  const goPrev = useCallback(async () => {
    if (cursor <= 0) return
    const prev = cursor - 1
    setCursor(prev)
    await loadTaskById(taskIds[prev])
  }, [cursor, taskIds, loadTaskById])

  const goNext = useCallback(async () => {
    if (!projectId) return
    setTaskLoading(true)
    const cur = cursor
    const ids = taskIds
    try {
      const next = await getNextAnnotationTask(projectId)
      if (next) {
        setTaskIds((prev) => (prev.includes(next.id) ? prev : [...prev, next.id]))
        setCurrentTask(next)
        setReadOnly(next.status === 'completed')
        setCursor(ids.indexOf(next.id) === -1 ? ids.length : ids.indexOf(next.id))
        return
      }
    } catch {
      /* fallthrough to local list */
    } finally {
      setTaskLoading(false)
    }
    if (cur < ids.length - 1) {
      const nxt = cur + 1
      setCursor(nxt)
      await loadTaskById(ids[nxt])
      return
    }
    setCurrentTask(null)
  }, [cursor, taskIds, projectId, loadTaskById])

  const refreshCurrentTask = useCallback(async () => {
    if (!currentTask) return
    const fresh = await getAnnotationTaskDetail(currentTask.id)
    setCurrentTask(fresh)
    setReadOnly(fresh.status === 'completed')
  }, [currentTask])

  // 初始化：加载我的任务列表 + 第一个任务
  useEffect(() => {
    if (!projectId || initialized) return
    setInitialized(true)
    void (async () => {
      setTaskLoading(true)
      try {
        const ids = await getMyProjectTaskIds(projectId)
        setTaskIds(ids)
        if (ids.length === 0) {
          setCurrentTask(null)
          return
        }
        const next = await getNextAnnotationTask(projectId)
        if (next) {
          setCurrentTask(next)
          setReadOnly(next.status === 'completed')
          const existingIdx = ids.indexOf(next.id)
          if (existingIdx >= 0) {
            setCursor(existingIdx)
          } else {
            setTaskIds((prev) => [...prev, next.id])
            setCursor(ids.length)
          }
        } else {
          await loadTaskById(ids[0])
          setCursor(0)
        }
      } catch {
        setTaskLoadFailed(true)
        getMessageInstance()?.error('加载任务失败')
      } finally {
        setTaskLoading(false)
      }
    })()
  }, [projectId, initialized, loadTaskById])

  // 全局方向键导航
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.altKey || e.ctrlKey || e.metaKey) return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        void goPrev()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        void goNext()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [goPrev, goNext])

  return {
    taskIds,
    cursor,
    currentTask,
    readOnly,
    taskLoading,
    taskLoadFailed,
    initialized,
    loadTaskById,
    goPrev,
    goNext,
    refreshCurrentTask,
    setCurrentTask,
    setReadOnly,
  }
}
