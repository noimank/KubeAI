import { useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'
import { getAccessUrl } from '@/services/dev-environments'
import { useDevEnvList } from './hooks/useDevEnvList'
import { DevEnvList } from './components/DevEnvList'
import { CreateModal } from './components/CreateModal'

export default function DevEnvironmentsPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const algorithmId = searchParams.get('algorithmId')

  const list = useDevEnvList()
  const [modalOpen, setModalOpen] = useState(!!algorithmId)

  const canWrite = useRbacStore((s) => s.hasPermission('dev_environments:write'))
  const canManage = useRbacStore((s) => s.hasPermission('dev_environments:manage'))
  const currentUserId = useAuthStore((s) => s.user?.id)

  const handleOpenEnvironment = async (envId: string) => {
    try {
      const res = await getAccessUrl(envId)
      if (res.accessUrl) {
        const token = useAuthStore.getState().accessToken
        if (token) {
          const securePart = location.protocol === 'https:' ? '; secure' : ''
          document.cookie = `kubeai_access_token=${token}; path=/; samesite=lax; max-age=86400${securePart}`
        }
        window.open(res.accessUrl, '_blank')
      }
    } catch {
      getMessageInstance()?.error('获取环境访问地址失败')
    }
  }

  const openCreateModal = () => setModalOpen(true)

  const closeCreateModal = () => {
    setModalOpen(false)
    if (algorithmId) {
      navigate('/dev-environments', { replace: true })
    }
  }

  const handleCreateSuccess = (values: Parameters<typeof list.create.mutate>[0]) => {
    list.create.mutate(values, {
      onSuccess: () => {
        setModalOpen(false)
        if (algorithmId) {
          navigate('/dev-environments', { replace: true })
        }
      },
    })
  }

  return (
    <>
      <DevEnvList
        data={list.data}
        loading={list.isLoading}
        page={list.page}
        pageSize={list.pageSize}
        statusFilter={list.statusFilter}
        onPageChange={list.onPageChange}
        onStatusChange={list.onStatusChange}
        onSearch={list.onSearch}
        onOpenEnv={handleOpenEnvironment}
        onStop={list.stop.mutate}
        onStart={list.start.mutate}
        onDelete={list.del.mutate}
        canWrite={canWrite}
        canManage={canManage}
        currentUserId={currentUserId}
        onCreateClick={openCreateModal}
      />
      <CreateModal
        open={modalOpen}
        algorithmId={algorithmId}
        submitting={list.create.isPending}
        onClose={closeCreateModal}
        onSubmit={handleCreateSuccess}
      />
    </>
  )
}
