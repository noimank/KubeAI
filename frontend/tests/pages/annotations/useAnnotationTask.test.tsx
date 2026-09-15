import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { AnnotationTask } from '@/types/annotation'
import { useAnnotationTask } from '@/pages/annotations/hooks/useAnnotationTask'
import {
  getAnnotationTaskDetail,
  getMyProjectTaskIds,
  getNextAnnotationTask,
} from '@/services/annotations'

vi.mock('@/services/annotations', () => ({
  getMyProjectTaskIds: vi.fn(),
  getNextAnnotationTask: vi.fn(),
  getAnnotationTaskDetail: vi.fn(),
}))

const mockedIds = vi.mocked(getMyProjectTaskIds)
const mockedNext = vi.mocked(getNextAnnotationTask)
const mockedDetail = vi.mocked(getAnnotationTaskDetail)

const T1 = '00000000-0000-0000-0000-000000000001'
const T2 = '00000000-0000-0000-0000-000000000002'
const T3 = '00000000-0000-0000-0000-000000000003'

function makeTask(id: string, status: AnnotationTask['status'] = 'assigned'): AnnotationTask {
  return {
    id,
    projectId: 'p1',
    data: {},
    status,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  }
}

/** 初始化到 ids 列表的 start 索引(next-task 落点语义) */
async function setupAt(
  ids: string[],
  start: number,
  detailStatus: AnnotationTask['status'] = 'assigned',
) {
  mockedIds.mockResolvedValue({ taskIds: ids, completedCount: 0 })
  mockedNext.mockResolvedValue(makeTask(ids[start]))
  mockedDetail.mockImplementation(async (tid: string) => makeTask(tid, detailStatus))
  const wrapper = renderHook(() => useAnnotationTask('p1'))
  await waitFor(() => expect(wrapper.result.current.currentTask?.id).toBe(ids[start]))
  return wrapper
}

describe('useAnnotationTask', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('初始化落点', () => {
    it('以 next-task 返回的待办为落点,cursor 指向其在列表中的位置', async () => {
      const { result } = await setupAt([T1, T2, T3], 1)
      expect(result.current.cursor).toBe(1)
      expect(result.current.taskIds).toEqual([T1, T2, T3])
    })

    it('next-task 返回 null(全部完成)时定位到第一条', async () => {
      mockedIds.mockResolvedValue({ taskIds: [T1, T2], completedCount: 2 })
      mockedNext.mockResolvedValue(null)
      mockedDetail.mockResolvedValue(makeTask(T1, 'completed'))
      const { result } = renderHook(() => useAnnotationTask('p1'))
      await waitFor(() => expect(result.current.currentTask?.id).toBe(T1))
      expect(result.current.cursor).toBe(0)
    })

    it('落点任务不在列表中(查询间隙新分配)时追加到列表尾部', async () => {
      mockedIds.mockResolvedValue({ taskIds: [T1], completedCount: 0 })
      mockedNext.mockResolvedValue(makeTask(T2))
      const { result } = renderHook(() => useAnnotationTask('p1'))
      await waitFor(() => expect(result.current.currentTask?.id).toBe(T2))
      expect(result.current.taskIds).toEqual([T1, T2])
      expect(result.current.cursor).toBe(1)
    })

    it('没有分配任务时 currentTask 为空', async () => {
      mockedIds.mockResolvedValue({ taskIds: [], completedCount: 0 })
      mockedNext.mockResolvedValue(null)
      const { result } = renderHook(() => useAnnotationTask('p1'))
      await waitFor(() => expect(result.current.initialized).toBe(true))
      expect(result.current.currentTask).toBeNull()
    })
  })

  describe('线性导航', () => {
    it('goNext 前进到下一条,序号恒为 cursor+1', async () => {
      const { result } = await setupAt([T1, T2, T3], 0)
      await act(async () => {
        await result.current.goNext()
      })
      expect(result.current.cursor).toBe(1)
      expect(result.current.currentTask?.id).toBe(T2)
      expect(mockedDetail).toHaveBeenCalledWith(T2)
    })

    it('goPrev 回退一条', async () => {
      const { result } = await setupAt([T1, T2, T3], 1)
      await act(async () => {
        await result.current.goPrev()
      })
      expect(result.current.cursor).toBe(0)
      expect(result.current.currentTask?.id).toBe(T1)
    })

    it('首条 goPrev / 末条 goNext 不移动', async () => {
      const { result } = await setupAt([T1, T2], 0)
      await act(async () => {
        await result.current.goPrev()
      })
      expect(result.current.cursor).toBe(0)
      expect(result.current.currentTask?.id).toBe(T1)

      const { result: last } = await setupAt([T1, T2], 1)
      let moved = true
      await act(async () => {
        moved = await last.current.goNext()
      })
      expect(moved).toBe(false)
      expect(last.current.cursor).toBe(1)
      expect(last.current.currentTask?.id).toBe(T2)
    })

    it('加载期间重复触发导航被忽略(防连点错位)', async () => {
      mockedIds.mockResolvedValue({ taskIds: [T1, T2, T3], completedCount: 0 })
      mockedNext.mockResolvedValue(makeTask(T1))
      let release!: (t: AnnotationTask) => void
      mockedDetail.mockImplementation(
        () =>
          new Promise<AnnotationTask>((resolve) => {
            release = resolve
          }),
      )
      const { result } = renderHook(() => useAnnotationTask('p1'))
      await waitFor(() => expect(result.current.currentTask?.id).toBe(T1))

      await act(async () => {
        void result.current.goNext() // 挂起在 detail 请求
        await result.current.goNext() // 应被导航锁拦截
        release(makeTask(T2))
        await Promise.resolve()
      })
      await waitFor(() => expect(result.current.currentTask?.id).toBe(T2))
      expect(mockedDetail).toHaveBeenCalledTimes(1)
      expect(result.current.cursor).toBe(1)
    })
  })

  describe('提交后流转', () => {
    it('刷新列表与完成计数,前进到提交任务的下一条', async () => {
      const { result } = await setupAt([T1, T2, T3], 0)
      // 提交 T1 后:列表完成计数 +1
      mockedIds.mockResolvedValue({ taskIds: [T1, T2, T3], completedCount: 1 })
      await act(async () => {
        await result.current.advanceAfterSubmit()
      })
      expect(result.current.completedCount).toBe(1)
      expect(result.current.cursor).toBe(1)
      expect(result.current.currentTask?.id).toBe(T2)
    })

    it('提交最后一条时停留在当前任务并转只读', async () => {
      const { result } = await setupAt([T1, T2], 1)
      mockedIds.mockResolvedValue({ taskIds: [T1, T2], completedCount: 2 })
      mockedDetail.mockResolvedValue(makeTask(T2, 'completed'))
      await act(async () => {
        await result.current.advanceAfterSubmit()
      })
      expect(result.current.cursor).toBe(1)
      expect(result.current.currentTask?.id).toBe(T2)
      expect(result.current.readOnly).toBe(true)
    })
  })

  describe('方向键热键', () => {
    it('ArrowRight 触发前进,长按(repeat)忽略', async () => {
      const { result } = await setupAt([T1, T2], 0)
      await act(async () => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
      })
      await waitFor(() => expect(result.current.currentTask?.id).toBe(T2))

      await act(async () => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', repeat: true }))
      })
      // 落点初始化不走 detail;仅热键前进调用 1 次,repeat 事件被忽略
      expect(mockedDetail).toHaveBeenCalledTimes(1)
    })

    it('输入框聚焦时不触发导航', async () => {
      const { result } = await setupAt([T1, T2], 0)
      const input = document.createElement('input')
      document.body.appendChild(input)
      await act(async () => {
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))
      })
      expect(result.current.currentTask?.id).toBe(T1)
    })
  })
})
