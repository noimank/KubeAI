import { useState, useCallback } from 'react'
import { Button, Input } from 'antd'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { deleteAnnotationProject, getAnnotationProjects } from '@/services/annotations'
import AnnotationProjectTable from './components/AnnotationProjectTable'
import CreateProjectModal from './components/CreateProjectModal'

export default function AnnotationsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')
  const [createModalOpen, setCreateModalOpen] = useState(false)

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('annotations:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['annotationProjects', page, pageSize, keyword],
    queryFn: () => getAnnotationProjects({ current: page, pageSize, keyword }),
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handlePageChange = useCallback((p: number, ps: number) => {
    setPage(p)
    setPageSize(ps)
  }, [])

  const handleDelete = async (id: string) => {
    try {
      await deleteAnnotationProject(id)
      getMessageInstance()?.success('标注项目删除成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjects'] })
    } catch {
      // interceptor handles error toast
    }
  }

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Input.Search
          placeholder="搜索标注项目名称"
          allowClear
          style={{ width: 280 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
        {canManage && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            创建标注项目
          </Button>
        )}
      </div>

      <AnnotationProjectTable
        data={data?.items}
        loading={isLoading}
        total={data?.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={handlePageChange}
        onDelete={handleDelete}
        canManage={canManage}
      />

      <CreateProjectModal open={createModalOpen} onClose={() => setCreateModalOpen(false)} />
    </div>
  )
}
