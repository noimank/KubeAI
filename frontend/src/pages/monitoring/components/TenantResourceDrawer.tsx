import { Descriptions, Divider, Drawer, Spin, Table } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getTenantResourceDetail } from '@/services/monitoring'
import type { JobSummary, ServiceSummary, TenantResourceDetail as Detail } from '@/types/monitoring'
import { formatKi, parseK8sQuantity } from '@/utils/format'

interface Props {
  tenantId: string | null
  onClose: () => void
}

function toNum(v: number | string): number {
  return parseK8sQuantity(v)
}

function formatMemDisplay(v: number | string): string {
  return formatKi(parseK8sQuantity(v))
}

function formatCpuDisplay(v: number | string): string {
  const cores = parseK8sQuantity(v)
  return cores % 1 === 0 ? `${cores} 核` : `${cores.toFixed(1)} 核`
}

const jobColumns = [
  { title: '任务名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'GPU', dataIndex: 'gpuCount', key: 'gpuCount', width: 60 },
]

const serviceColumns = [
  { title: '服务名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: 'GPU', dataIndex: 'gpuCount', key: 'gpuCount', width: 60 },
]

export default function TenantResourceDrawer({ tenantId, onClose }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['monitoringTenantDetail', tenantId],
    queryFn: async () => {
      if (!tenantId) return null
      const res = await getTenantResourceDetail(tenantId)
      return res.data
    },
    enabled: !!tenantId,
  })

  const detail: Detail | null = data ?? null

  return (
    <Drawer
      title={detail?.tenantName ?? '租户详情'}
      open={!!tenantId}
      onClose={onClose}
      width={600}
    >
      {isLoading || !detail ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="GPU 使用">
              {toNum(detail.gpu.used)} / {toNum(detail.gpu.quota)}
            </Descriptions.Item>
            <Descriptions.Item label="CPU 使用">
              {formatCpuDisplay(detail.cpu.used)} / {formatCpuDisplay(detail.cpu.quota)}
            </Descriptions.Item>
            <Descriptions.Item label="内存使用">
              {formatMemDisplay(detail.memory.used)} / {formatMemDisplay(detail.memory.quota)}
            </Descriptions.Item>
            <Descriptions.Item label="存储使用">
              {formatMemDisplay(detail.storage.used)} / {formatMemDisplay(detail.storage.quota)}
            </Descriptions.Item>
          </Descriptions>

          <Divider>活跃训练任务 ({detail.activeJobs.length})</Divider>
          <Table<JobSummary>
            rowKey="id"
            columns={jobColumns}
            dataSource={detail.activeJobs}
            pagination={false}
            size="small"
            locale={{ emptyText: '暂无活跃任务' }}
          />

          <Divider>推理服务 ({detail.runningServices.length})</Divider>
          <Table<ServiceSummary>
            rowKey="id"
            columns={serviceColumns}
            dataSource={detail.runningServices}
            pagination={false}
            size="small"
            locale={{ emptyText: '暂无推理服务' }}
          />
        </>
      )}
    </Drawer>
  )
}
