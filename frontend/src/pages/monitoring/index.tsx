import { useState } from 'react'
import { Button, Card, Col, message, Row, Tabs, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getClusterOverview,
  getNodeDetails,
  getOrphanPVCs,
  getQuotaAllocationOverview,
  getQuotaComparison,
  getStaleJobs,
  getTenantResourceSummary,
  triggerCleanup,
} from '@/services/monitoring'
import type { TenantQuotaComparison } from '@/types/monitoring'
import ClusterOverviewCards from './components/ClusterOverviewCards'
import NodeResourceTable from './components/NodeResourceTable'
import TenantResourceTable from './components/TenantResourceTable'
import TenantResourceDrawer from './components/TenantResourceDrawer'
import QuotaAllocationBar from './components/QuotaAllocationBar'
import TenantQuotaTable from './components/TenantQuotaTable'
import QuotaTransferModal from './components/QuotaTransferModal'
import StaleJobTable from './components/StaleJobTable'
import OrphanPVCTable from './components/OrphanPVCTable'

export default function MonitoringPage() {
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null)
  const [transferOpen, setTransferOpen] = useState(false)
  const [transferFrom, setTransferFrom] = useState<TenantQuotaComparison | undefined>()

  const { data: overviewRes, isLoading: overviewLoading } = useQuery({
    queryKey: ['clusterOverview'],
    queryFn: getClusterOverview,
    refetchInterval: 30_000,
  })

  const { data: nodesRes, isLoading: nodesLoading } = useQuery({
    queryKey: ['clusterNodes'],
    queryFn: getNodeDetails,
    refetchInterval: 30_000,
  })

  const { data: tenantsRes, isLoading: tenantsLoading } = useQuery({
    queryKey: ['monitoringTenants'],
    queryFn: getTenantResourceSummary,
    refetchInterval: 30_000,
  })

  const { data: allocationRes, isLoading: allocationLoading } = useQuery({
    queryKey: ['quotaAllocation'],
    queryFn: getQuotaAllocationOverview,
    refetchInterval: 30_000,
  })

  const {
    data: comparisonRes,
    isLoading: comparisonLoading,
    refetch: refetchComparison,
  } = useQuery({
    queryKey: ['quotaComparison'],
    queryFn: getQuotaComparison,
    refetchInterval: 30_000,
  })

  const queryClient = useQueryClient()

  const { data: staleJobsRes, isLoading: staleJobsLoading } = useQuery({
    queryKey: ['staleJobs'],
    queryFn: getStaleJobs,
    refetchInterval: 30_000,
  })

  const {
    data: orphanPVCsRes,
    isLoading: orphanPVCsLoading,
    refetch: refetchOrphanPVCs,
  } = useQuery({
    queryKey: ['orphanPVCs'],
    queryFn: getOrphanPVCs,
    refetchInterval: 30_000,
  })

  const handleTransfer = (tenant?: TenantQuotaComparison) => {
    setTransferFrom(tenant)
    setTransferOpen(true)
  }

  const handleTransferSuccess = () => {
    refetchComparison()
  }

  const handleTriggerCleanup = async () => {
    try {
      const res = await triggerCleanup()
      if (res.success) {
        message.success('清理任务已触发')
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ['staleJobs'] })
          refetchOrphanPVCs()
        }, 3000)
      } else {
        message.error(res.message || '触发失败')
      }
    } catch {
      message.error('触发清理请求失败')
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>集群资源监控</Typography.Title>

      <Tabs
        defaultActiveKey="overview"
        items={[
          {
            key: 'overview',
            label: '资源概览',
            children: (
              <>
                <ClusterOverviewCards data={overviewRes?.data ?? null} loading={overviewLoading} />
                <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
                  <Col xs={24} xl={12}>
                    <Card title="节点资源" size="small">
                      <NodeResourceTable data={nodesRes?.data ?? []} loading={nodesLoading} />
                    </Card>
                  </Col>
                  <Col xs={24} xl={12}>
                    <Card title="租户资源" size="small">
                      <TenantResourceTable
                        data={tenantsRes?.data ?? []}
                        loading={tenantsLoading}
                        onRowClick={(id) => setSelectedTenantId(id)}
                      />
                    </Card>
                  </Col>
                </Row>
              </>
            ),
          },
          {
            key: 'quota',
            label: '配额管理',
            children: (
              <>
                <Card title="集群资源分配概览" size="small" style={{ marginBottom: 16 }}>
                  <QuotaAllocationBar
                    data={allocationRes?.data ?? null}
                    loading={allocationLoading}
                  />
                </Card>
                <Card title="租户配额对比" size="small">
                  <TenantQuotaTable
                    data={comparisonRes?.data ?? []}
                    loading={comparisonLoading}
                    onTransfer={handleTransfer}
                  />
                </Card>
              </>
            ),
          },
          {
            key: 'cleanup',
            label: '资源清理',
            children: (
              <>
                <div style={{ marginBottom: 16, textAlign: 'right' }}>
                  <Button type="primary" onClick={handleTriggerCleanup}>
                    立即清理
                  </Button>
                </div>
                <Card title="过期任务资源" size="small" style={{ marginBottom: 16 }}>
                  <StaleJobTable data={staleJobsRes?.data ?? []} loading={staleJobsLoading} />
                </Card>
                <Card title="孤立 PVC" size="small">
                  <OrphanPVCTable
                    data={orphanPVCsRes?.data ?? []}
                    loading={orphanPVCsLoading}
                    onRefresh={refetchOrphanPVCs}
                  />
                </Card>
              </>
            ),
          },
        ]}
      />

      <TenantResourceDrawer tenantId={selectedTenantId} onClose={() => setSelectedTenantId(null)} />

      <QuotaTransferModal
        open={transferOpen}
        tenants={comparisonRes?.data ?? []}
        preselectedTenant={transferFrom}
        onClose={() => {
          setTransferOpen(false)
          setTransferFrom(undefined)
        }}
        onSuccess={handleTransferSuccess}
      />
    </div>
  )
}
