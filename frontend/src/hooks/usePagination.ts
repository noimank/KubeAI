import { useState, useCallback } from 'react'

interface PaginationState {
  page: number
  pageSize: number
  total: number
}

export function usePagination(defaultPageSize = 10) {
  const [pagination, setPagination] = useState<PaginationState>({
    page: 1,
    pageSize: defaultPageSize,
    total: 0,
  })

  const setPage = useCallback((page: number) => {
    setPagination((prev) => ({ ...prev, page }))
  }, [])

  const setPageSize = useCallback((pageSize: number) => {
    setPagination((prev) => ({ ...prev, pageSize, page: 1 }))
  }, [])

  const setTotal = useCallback((total: number) => {
    setPagination((prev) => ({ ...prev, total }))
  }, [])

  const onChange = useCallback((page: number, pageSize: number) => {
    setPagination({ page, pageSize, total: 0 })
  }, [])

  return {
    page: pagination.page,
    pageSize: pagination.pageSize,
    total: pagination.total,
    setPage,
    setPageSize,
    setTotal,
    onChange,
  }
}
