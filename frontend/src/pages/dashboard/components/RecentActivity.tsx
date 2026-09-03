import { Card, Col, Row } from 'antd'
import type { DashboardResponse } from '@/types/dashboard'
import RecentTrainingJobs from './RecentTrainingJobs'
import RecentDatasets from './RecentDatasets'
import RecentInferenceServices from './RecentInferenceServices'
import PendingAnnotationProjects from './PendingAnnotationProjects'

interface Props {
  data: DashboardResponse | null
}

export default function RecentActivity({ data }: Props) {
  const training = data?.recentTrainingJobs ?? null
  const datasets = data?.recentDatasets ?? null
  const inference = data?.recentInferenceServices ?? null
  const annotations = data?.pendingAnnotations ?? null

  if (!training && !datasets && !inference && !annotations) return null

  return (
    <section className="dash-section">
      <div className="dash-section-head">
        <span className="dash-section-title">最近动态</span>
        <span className="dash-section-subtitle">您近期的工作与平台动态</span>
      </div>
      <Row gutter={[16, 16]}>
        {training && (
          <Col xs={24} lg={datasets ? 14 : 24}>
            <Card title="最近训练任务" size="small">
              <RecentTrainingJobs data={training} />
            </Card>
          </Col>
        )}
        {datasets && (
          <Col xs={24} lg={training ? 10 : 24}>
            <Card title="最近数据集" size="small">
              <RecentDatasets data={datasets} />
            </Card>
          </Col>
        )}
        {inference && (
          <Col span={24}>
            <Card title="最近推理服务" size="small">
              <RecentInferenceServices data={inference} />
            </Card>
          </Col>
        )}
        {annotations && (
          <Col span={24}>
            <Card title="我的标注待办" size="small">
              <PendingAnnotationProjects data={annotations} />
            </Card>
          </Col>
        )}
      </Row>
    </section>
  )
}
