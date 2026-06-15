import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import {
  getDevEnvironments,
  createDevEnvironment,
  stopDevEnvironment,
  startDevEnvironment,
  deleteDevEnvironment,
} from '@/services/dev-environments'
import type { DevEnvironmentCreateParams } from '@/types/dev-environment'

export function useDevEnvList() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [keyword, setKeyword] = useState<string | undefined>(undefined)

  const { data, isLoading } = useQuery({
    queryKey: ['devEnvironments', page, pageSize, statusFilter, keyword],
    queryFn: () =>
      getDevEnvironments({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        name: keyword,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const hasActive = items.some(
        (env) => env.status === 'pending' || env.status === 'starting' || env.status === 'stopping',
      )
      return hasActive ? 3000 : false
    },
  })

  const onPageChange = useCallback((p: number, ps: number) => {
    setPage(p)
    setPageSize(ps)
  }, [])

  const onStatusChange = useCallback((val: string) => {
    setStatusFilter(val)
    setPage(1)
  }, [])

  const onSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const create = useMutation({
    mutationFn: (values: DevEnvironmentCreateParams) => createDevEnvironment(values),
    onSuccess: () => {
      getMessageInstance()?.success('开发环境创建任务已提交')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const stop = useMutation({
    mutationFn: stopDevEnvironment,
    onSuccess: () => {
      getMessageInstance()?.success('停止任务已提交，请稍候')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const start = useMutation({
    mutationFn: startDevEnvironment,
    onSuccess: () => {
      getMessageInstance()?.success('启动任务已提交，请稍候')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const del = useMutation({
    mutationFn: deleteDevEnvironment,
    onSuccess: () => {
      getMessageInstance()?.success('删除任务已提交')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  return {
    page,
    pageSize,
    statusFilter,
    data,
    isLoading,
    onPageChange,
    onStatusChange,
    onSearch,
    create,
    stop,
    start,
    del,
  }
}
