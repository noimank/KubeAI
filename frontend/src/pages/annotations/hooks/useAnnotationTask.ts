import { useCallback, useEffect, useRef, useState } from 'react'
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
 * 导航模型（对齐 Label Studio 任务流）：上一个/下一个 = 稳定有序的「我的任务」
 * 列表（created_at 升序）上的游标移动，序号永远 ±1，不依赖服务端的任务分发
 * 顺序；next-task 接口仅在进入工作台时决定落点（回到最靠前的待办任务）。
 *
 * globalResults 的重置由调用方通过监听 currentTask?.id 变化的 effect 处理，
 * 保持本 hook 单一职责（任务流转）。
 */
export interface UseAnnotationTaskReturn {
  taskIds: string[]
  /** 当前用户在项目内已完成的任务数（进度以「我的任务」为口径） */
  completedCount: number
  cursor: number
  currentTask: AnnotationTask | null
  readOnly: boolean
  taskLoading: boolean
  taskLoadFailed: boolean
  initialized: boolean
  goPrev: () => Promise<void>
  /** 前进到列表中的下一条；已在末尾时提示并返回 false */
  goNext: () => Promise<boolean>
  /** 提交成功后的流转：刷新列表与进度后前进；没有下一条则停留并转只读 */
  advanceAfterSubmit: () => Promise<void>
  /** 重新标注流：刷新当前任务并更新只读态 */
  refreshCurrentTask: () => Promise<void>
}

export function useAnnotationTask(projectId: string | undefined): UseAnnotationTaskReturn {
  const [taskIds, setTaskIds] = useState<string[]>([])
  const [completedCount, setCompletedCount] = useState(0)
  const [cursor, setCursor] = useState(0)
  const [currentTask, setCurrentTask] = useState<AnnotationTask | null>(null)
  const [readOnly, setReadOnly] = useState(false)
  const [taskLoading, setTaskLoading] = useState(false)
  const [taskLoadFailed, setTaskLoadFailed] = useState(false)
  const [initialized, setInitialized] = useState(false)

  // 导航防重入：加载期间忽略按钮/热键触发，避免并发请求导致任务与序号错位
  const navLockRef = useRef(false)

  const applyTask = useCallback((task: AnnotationTask) => {
    setCurrentTask(task)
    setReadOnly(task.status === 'completed')
  }, [])

  const navigateTo = useCallback(
    async (ids: string[], index: number): Promise<boolean> => {
      const tid = ids[index]
      if (!tid) return false
      navLockRef.current = true
      setTaskLoading(true)
      setTaskLoadFailed(false)
      setCursor(index)
      try {
        applyTask(await getAnnotationTaskDetail(tid))
        return true
      } catch {
        setTaskLoadFailed(true)
        getMessageInstance()?.error('加载任务失败')
        return false
      } finally {
        navLockRef.current = false
        setTaskLoading(false)
      }
    },
    [applyTask],
  )

  const goPrev = useCallback(async () => {
    if (navLockRef.current || cursor <= 0) return
    await navigateTo(taskIds, cursor - 1)
  }, [cursor, taskIds, navigateTo])

  const goNext = useCallback(async (): Promise<boolean> => {
    if (navLockRef.current) return false
    if (cursor >= taskIds.length - 1) {
      getMessageInstance()?.info('已是最后一个任务')
      return false
    }
    return navigateTo(taskIds, cursor + 1)
  }, [cursor, taskIds, navigateTo])

  const refreshCurrentTask = useCallback(async () => {
    if (!currentTask) return
    const fresh = await getAnnotationTaskDetail(currentTask.id)
    applyTask(fresh)
    // 撤销提交等场景：任务从 completed 回到进行中，同步回退进度计数
    if (currentTask.status === 'completed' && fresh.status !== 'completed') {
      setCompletedCount((c) => Math.max(0, c - 1))
    }
  }, [currentTask, applyTask])

  const advanceAfterSubmit = useCallback(async () => {
    if (!projectId || !currentTask) return
    try {
      const { taskIds: ids, completedCount: completed } = await getMyProjectTaskIds(projectId)
      setTaskIds(ids)
      setCompletedCount(completed)
      const curIdx = ids.indexOf(currentTask.id)
      if (curIdx >= 0 && curIdx < ids.length - 1) {
        await navigateTo(ids, curIdx + 1)
      } else {
        await refreshCurrentTask()
        getMessageInstance()?.info('已是最后一个任务')
      }
    } catch {
      getMessageInstance()?.error('刷新任务列表失败')
    }
  }, [projectId, currentTask, navigateTo, refreshCurrentTask])

  // 初始化：加载我的任务列表，以服务端最优先待办为落点（继续未完成的工作）
  useEffect(() => {
    if (!projectId || initialized) return
    setInitialized(true)
    void (async () => {
      navLockRef.current = true
      setTaskLoading(true)
      try {
        const { taskIds: ids, completedCount: completed } = await getMyProjectTaskIds(projectId)
        setTaskIds(ids)
        setCompletedCount(completed)
        if (ids.length === 0) {
          setCurrentTask(null)
          return
        }
        try {
          const next = await getNextAnnotationTask(projectId)
          if (next) {
            applyTask(next)
            const idx = ids.indexOf(next.id)
            if (idx >= 0) {
              setCursor(idx)
            } else {
              // 列表查询与落点查询之间的新分配任务：追加到列表尾部
              setTaskIds([...ids, next.id])
              setCursor(ids.length)
            }
            return
          }
        } catch {
          /* 落点查询失败时退回列表第一条 */
        }
        await navigateTo(ids, 0)
      } catch {
        setTaskLoadFailed(true)
        getMessageInstance()?.error('加载任务失败')
      } finally {
        navLockRef.current = false
        setTaskLoading(false)
      }
    })()
  }, [projectId, initialized, applyTask, navigateTo])

  // 全局方向键导航
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.repeat) return
      const target = e.target as HTMLElement | null
      if (target?.isContentEditable) return
      const tag = target?.tagName
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
    completedCount,
    cursor,
    currentTask,
    readOnly,
    taskLoading,
    taskLoadFailed,
    initialized,
    goPrev,
    goNext,
    advanceAfterSubmit,
    refreshCurrentTask,
  }
}
