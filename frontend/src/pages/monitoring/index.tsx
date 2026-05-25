import { useState } from 'react'
import { Card, Col, Row, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getClusterOverview, getNodeDetails, getTenantResourceSummary } from '@/services/monitoring'
import ClusterOverviewCards from './components/ClusterOverviewCards'
import NodeResourceTable from './components/NodeResourceTable'
import TenantResourceTable from './components/TenantResourceTable'
import TenantResourceDrawer from './components/TenantResourceDrawer'

export default function MonitoringPage() {
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null)

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

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3}>集群资源监控</Typography.Title>

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

      <TenantResourceDrawer tenantId={selectedTenantId} onClose={() => setSelectedTenantId(null)} />
    </div>
  )
}
