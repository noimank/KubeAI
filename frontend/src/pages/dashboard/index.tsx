import { Card, Col, Row, Skeleton, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useRbacStore } from '@/stores/rbacStore'
import { getDashboard } from '@/services/dashboard'
import FirstLoginGuide from '@/components/FirstLoginGuide'
import type {
  AdminDashboard,
  AnnotatorDashboard,
  EngineerDashboard,
  MLOpsDashboard,
} from '@/types/dashboard'
import ResourceOverviewCards from './components/ResourceOverviewCards'
import RecentTrainingJobs from './components/RecentTrainingJobs'
import RecentDatasets from './components/RecentDatasets'
import ClusterOverviewSection from './components/ClusterOverviewSection'
import TenantRankingTable from './components/TenantRankingTable'
import RecentAlerts from './components/RecentAlerts'
import AnnotationProgressCards from './components/AnnotationProgressCards'
import PendingAnnotationTasks from './components/PendingAnnotationTasks'
import RecentInferenceServices from './components/RecentInferenceServices'

export default function DashboardPage() {
  const role = useRbacStore((s) => s.currentRole)

  const { data, isLoading } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    refetchInterval: 30_000,
    enabled: !!role,
  })

  const dashboardData = data?.data

  return (
    <div>
      <Typography.Title level={3} style={{ marginBottom: 24 }}>
        系统概览
      </Typography.Title>

      {isLoading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : role === 'admin' ? (
        <AdminLayout data={dashboardData?.data as AdminDashboard | undefined} />
      ) : role === 'annotator' ? (
        <AnnotatorLayout data={dashboardData?.data as AnnotatorDashboard | undefined} />
      ) : role === 'mlops' ? (
        <MLOpsLayout data={dashboardData?.data as MLOpsDashboard | undefined} />
      ) : (
        <EngineerLayout data={dashboardData?.data as EngineerDashboard | undefined} />
      )}
      <FirstLoginGuide />
    </div>
  )
}

function EngineerLayout({ data }: { data?: EngineerDashboard }) {
  return (
    <>
      <ResourceOverviewCards data={data?.resourceOverview ?? null} loading={!data} />
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="最近训练任务" size="small">
            <RecentTrainingJobs data={data?.recentTrainingJobs ?? []} loading={!data} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="最近数据集" size="small">
            <RecentDatasets data={data?.recentDatasets ?? []} loading={!data} />
          </Card>
        </Col>
      </Row>
    </>
  )
}

function AdminLayout({ data }: { data?: AdminDashboard }) {
  return (
    <>
      <ClusterOverviewSection data={data?.clusterOverview ?? null} loading={!data} />
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card title="租户配额使用排行" size="small">
            <TenantRankingTable data={data?.tenantRanking ?? []} loading={!data} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="最近告警" size="small">
            <RecentAlerts data={data?.recentAlerts ?? []} loading={!data} />
          </Card>
        </Col>
      </Row>
    </>
  )
}

function AnnotatorLayout({ data }: { data?: AnnotatorDashboard }) {
  return (
    <>
      <AnnotationProgressCards data={data?.progressOverview ?? null} loading={!data} />
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="待办标注任务" size="small">
            <PendingAnnotationTasks data={data?.pendingTasks ?? []} loading={!data} />
          </Card>
        </Col>
      </Row>
    </>
  )
}

function MLOpsLayout({ data }: { data?: MLOpsDashboard }) {
  return (
    <>
      <ResourceOverviewCards data={data?.resourceOverview ?? null} loading={!data} />
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={24}>
          <Card title="最近推理服务" size="small">
            <RecentInferenceServices data={data?.recentInferenceServices ?? []} loading={!data} />
          </Card>
        </Col>
      </Row>
    </>
  )
}
