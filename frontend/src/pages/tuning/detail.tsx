import { useMemo, useState } from 'react'
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  ExperimentOutlined,
  InboxOutlined,
  SwapOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { Link, useParams } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate } from '@/utils/format'
import { TRAINING_JOB_STATUS_CONFIG } from '@/utils/constants'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'
import FileBrowser from '@/components/FileBrowser'
import { registerModel } from '@/services/models'
import {
  getBestTrial,
  getTuningInsights,
  getTuningStudy,
  getTuningTrials,
  pauseTuningStudy,
  resumeTuningStudy,
} from '@/services/tuning'
import OptimizationHistoryChart from './components/OptimizationHistoryChart'
import HyperparameterImportanceChart from './components/HyperparameterImportanceChart'
import ParallelCoordinatesChart from './components/ParallelCoordinatesChart'
import ExperimentCompareDrawer from './components/ExperimentCompareDrawer'
import type { TuningStudyStatus, TuningTrial, TuningTrialState } from '@/types/tuning'

const STUDY_STATUS_CONFIG: Record<TuningStudyStatus, { color: string; text: string }> = {
  running: { color: 'processing', text: '调优中' },
  completed: { color: 'success', text: '已完成' },
  stopped: { color: 'default', text: '已停止' },
  failed: { color: 'error', text: '已失败' },
  paused: { color: 'warning', text: '已暂停' },
}

const TRIAL_STATE_CONFIG: Record<TuningTrialState, { color: string; text: string }> = {
  pending: { color: 'default', text: '待运行' },
  running: { color: 'processing', text: '运行中' },
  complete: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
  pruned: { color: 'warning', text: '已剪枝' },
}

export default function TuningDetailPage() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('tuning:write')
  const canWriteModels = hasPermission('models:write')

  const [registerOpen, setRegisterOpen] = useState(false)
  const [modelName, setModelName] = useState('')
  const [modelDesc, setModelDesc] = useState('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  // trial 实验对比: 勾选 2-5 个有实验的 trial
  const [selectedTrialKeys, setSelectedTrialKeys] = useState<string[]>([])
  const [compareOpen, setCompareOpen] = useState(false)

  const authUser = useAuthStore((s) => s.user)
  const currentTenant = useTenantStore((s) => s.currentTenant)
  const browserRoots = useMemo<string[]>(
    () => (authUser && currentTenant ? ['/kubeai/home', '/kubeai/workspace'] : []),
    [authUser, currentTenant],
  )

  const { data: study, isLoading } = useQuery({
    queryKey: ['tuningStudy', id],
    queryFn: () => getTuningStudy(id!),
    enabled: !!id,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 5000 : false),
  })

  const { data: trials } = useQuery({
    queryKey: ['tuningTrials', id],
    queryFn: () => getTuningTrials(id!),
    enabled: !!id,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((t) => ['pending', 'running'].includes(t.state)) ? 5000 : false,
  })

  const { data: best } = useQuery({
    queryKey: ['tuningBest', id],
    queryFn: () => getBestTrial(id!),
    enabled: !!id,
  })

  const { data: insights } = useQuery({
    queryKey: ['tuningInsights', id],
    queryFn: () => getTuningInsights(id!),
    enabled: !!id,
    // 调优中 (含 trial 未起的空 history) 或 history 仍有运行中 trial 时每 10s 刷新;
    // 终态且无活动 trial 后停止轮询, 最后一次拉取保证收敛到最终数据.
    refetchInterval: (query) => {
      const hasActive = (query.state.data?.history ?? []).some(
        (t) => t.state === 'running' || t.state === 'pending',
      )
      return study?.status === 'running' || hasActive ? 10_000 : false
    },
  })

  const registerMutation = useMutation({
    mutationFn: registerModel,
    onSuccess: () => {
      getMessageInstance()?.success('模型注册成功')
      setRegisterOpen(false)
      queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })

  const pauseMutation = useMutation({
    mutationFn: pauseTuningStudy,
    onSuccess: () => {
      getMessageInstance()?.success('调优任务已暂停')
      queryClient.invalidateQueries({ queryKey: ['tuningStudy', id] })
    },
  })

  const resumeMutation = useMutation({
    mutationFn: resumeTuningStudy,
    onSuccess: () => {
      getMessageInstance()?.success('调优任务已恢复')
      queryClient.invalidateQueries({ queryKey: ['tuningStudy', id] })
    },
  })

  const openRegister = () => {
    setModelName(`${study?.name ?? 'tuning'}-best`)
    setModelDesc('由超参调优最优 trial 注册')
    setSelectedPaths([])
    setRegisterOpen(true)
  }

  // 勾选 trial 对应的实验 ID (无实验的 trial 不参与对比)
  const selectedExperimentIds = useMemo(
    () =>
      (trials ?? [])
        .filter((t) => selectedTrialKeys.includes(t.id) && t.experimentId)
        .map((t) => t.experimentId!),
    [trials, selectedTrialKeys],
  )

  const handleRegisterOk = () => {
    if (!selectedPaths.length) {
      getMessageInstance()?.warning('请至少勾选一个文件或目录')
      return
    }
    if (!best?.trainingJobId) return
    registerMutation.mutate({
      name: modelName,
      description: modelDesc || undefined,
      filePaths: selectedPaths,
      trainingJobId: best.trainingJobId,
    })
  }

  const columns: ColumnsType<TuningTrial> = [
    {
      title: '#',
      dataIndex: 'trialNumber',
      width: 60,
      render: (val: number) => <Tag>#{val}</Tag>,
    },
    {
      title: '超参数',
      key: 'params',
      render: (_, record: TuningTrial) => (
        <Space wrap size={[4, 4]}>
          {record.params
            ? Object.entries(record.params).map(([k, v]) => (
                <Tag key={k} style={{ marginBottom: 0 }}>
                  {k}={String(v)}
                </Tag>
              ))
            : '—'}
        </Space>
      ),
    },
    {
      title: '指标值',
      dataIndex: 'value',
      width: 120,
      render: (val: number | undefined) => (val === undefined || val === null ? '—' : String(val)),
    },
    {
      title: '状态',
      dataIndex: 'state',
      width: 100,
      render: (val: TuningTrialState) => {
        const cfg = TRIAL_STATE_CONFIG[val] ?? { color: 'default', text: val }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '训练任务',
      key: 'job',
      width: 260,
      render: (_, record: TuningTrial) => {
        if (!record.trainingJobId) return '已删除'
        const jobCfg = record.jobStatus
          ? (TRAINING_JOB_STATUS_CONFIG[record.jobStatus] ?? {
              color: 'default',
              text: record.jobStatus,
            })
          : null
        return (
          <Space size={4}>
            <Link to={`/training-jobs/${record.trainingJobId}`}>
              {record.jobName ?? '查看任务'}
            </Link>
            {jobCfg && <Tag color={jobCfg.color}>{jobCfg.text}</Tag>}
            {record.experimentId && (
              <Tooltip title="查看实验详情（超参数 / 指标曲线）">
                <Link to={`/training-jobs/${record.trainingJobId}?tab=experiment`}>
                  <ExperimentOutlined style={{ color: '#1890ff' }} />
                </Link>
              </Tooltip>
            )}
          </Space>
        )
      },
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 160,
      render: (val: string) => formatDate(val),
    },
  ]

  if (isLoading || !study) {
    return <div style={{ padding: 24 }}>加载中...</div>
  }

  const statusCfg = STUDY_STATUS_CONFIG[study.status] ?? { color: 'default', text: study.status }
  const progressPercent =
    study.nTrials > 0 ? Math.round((study.finalizedCount / study.nTrials) * 100) : 0
  const bestParams = best?.params
    ? Object.entries(best.params).map(([k, v]) => (
        <Tag key={k} style={{ marginBottom: 4 }}>
          {k}={String(v)}
        </Tag>
      ))
    : null

  return (
    <div style={{ padding: 0 }}>
      <Card
        title={
          <Space>
            <ThunderboltOutlined />
            {study.name}
            <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
          </Space>
        }
        extra={
          canWrite && (
            <Space>
              {study.status === 'running' && (
                <Popconfirm
                  title="确认暂停该调优任务？运行中的 trial 会被停止并释放资源。"
                  onConfirm={() => pauseMutation.mutate(study.id)}
                >
                  <Button size="small">暂停</Button>
                </Popconfirm>
              )}
              {study.status === 'paused' && (
                <Popconfirm
                  title="确认恢复该调优任务？将从此前进度继续补发 trial。"
                  onConfirm={() => resumeMutation.mutate(study.id)}
                >
                  <Button type="primary" size="small">
                    恢复
                  </Button>
                </Popconfirm>
              )}
            </Space>
          )
        }
        style={{ marginBottom: 16 }}
      >
        <Descriptions bordered size="small" column={3}>
          <Descriptions.Item label="目标指标">
            <Tag color={study.direction === 'minimize' ? 'blue' : 'orange'}>
              {study.direction === 'minimize' ? '最小化' : '最大化'}
            </Tag>
            {study.metricName}
          </Descriptions.Item>
          <Descriptions.Item label="试验总数">{study.nTrials}</Descriptions.Item>
          <Descriptions.Item label="并发试验数">{study.nJobs}</Descriptions.Item>
          <Descriptions.Item label="进度" span={3}>
            <Progress
              percent={progressPercent}
              size="small"
              format={() => `${study.finalizedCount}/${study.nTrials}`}
            />
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={3}>
            {study.description || '—'}
          </Descriptions.Item>
          {study.errorMessage && (
            <Descriptions.Item label="错误信息" span={3}>
              <Typography.Text type="danger">{study.errorMessage}</Typography.Text>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Card
        title="最优结果"
        size="small"
        extra={
          best?.trainingJobId &&
          canWriteModels && (
            <Button type="primary" icon={<InboxOutlined />} size="small" onClick={openRegister}>
              注册最佳模型
            </Button>
          )
        }
        style={{ marginBottom: 16 }}
      >
        {best?.value !== undefined && best?.value !== null ? (
          <Space align="center" size={24}>
            <Space size={8}>
              <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />
              <Typography.Text strong style={{ fontSize: 16 }}>
                {best.value}
              </Typography.Text>
            </Space>
            <Space wrap size={[4, 4]}>
              {bestParams}
            </Space>
            {best.trainingJobId && (
              <Link to={`/training-jobs/${best.trainingJobId}`}>查看最优 trial 训练任务</Link>
            )}
          </Space>
        ) : (
          <Empty description="暂无已完成 trial" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card title="优化历史" size="small" style={{ marginBottom: 16 }}>
        <OptimizationHistoryChart history={insights?.history ?? []} direction={study.direction} />
      </Card>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={24} md={10}>
          <Card title="超参重要性" size="small">
            <HyperparameterImportanceChart importance={insights?.importance ?? {}} />
          </Card>
        </Col>
        <Col xs={24} md={14}>
          <Card title="平行坐标" size="small">
            <ParallelCoordinatesChart
              history={insights?.history ?? []}
              importance={insights?.importance}
              metricName={study.metricName}
            />
          </Card>
        </Col>
      </Row>

      <Card title={`Trials（${study.trialCount}）`} size="small">
        <Table<TuningTrial>
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={trials ?? []}
          pagination={false}
          locale={{ emptyText: '暂无 trial' }}
          rowSelection={{
            selectedRowKeys: selectedTrialKeys,
            onChange: (keys) => setSelectedTrialKeys(keys as string[]),
            selections: false,
            getCheckboxProps: (record) => ({
              disabled:
                !record.experimentId ||
                (selectedTrialKeys.length >= 5 && !selectedTrialKeys.includes(record.id)),
            }),
          }}
        />
      </Card>

      {/* trial 实验对比浮动栏 */}
      {selectedTrialKeys.length > 0 && (
        <div
          style={{
            position: 'fixed',
            bottom: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 100,
            background: 'var(--ant-color-bg-container)',
            border: '1px solid var(--ant-color-border)',
            borderRadius: 8,
            padding: '8px 16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span>已选 {selectedTrialKeys.length} 个 trial（最多 5 个）</span>
          <Button
            type="primary"
            icon={<SwapOutlined />}
            disabled={selectedExperimentIds.length < 2}
            onClick={() => setCompareOpen(true)}
          >
            对比实验
          </Button>
          <Button onClick={() => setSelectedTrialKeys([])}>取消选择</Button>
        </div>
      )}
      <ExperimentCompareDrawer
        open={compareOpen}
        experimentIds={selectedExperimentIds}
        onClose={() => setCompareOpen(false)}
      />

      <Modal
        title="注册模型"
        open={registerOpen}
        onCancel={() => setRegisterOpen(false)}
        onOk={handleRegisterOk}
        confirmLoading={registerMutation.isPending}
        okText="确认注册"
        cancelText="取消"
        width={680}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Typography.Text strong>模型名称</Typography.Text>
            <Input
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="例如 my-model"
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>描述</Typography.Text>
            <Input
              value={modelDesc}
              onChange={(e) => setModelDesc(e.target.value)}
              placeholder="模型描述（可选）"
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>选择模型文件或目录</Typography.Text>
            <div style={{ marginTop: 4 }}>
              <FileBrowser value={selectedPaths} onChange={setSelectedPaths} roots={browserRoots} />
            </div>
          </div>
          <div>
            <Typography.Text strong>关联训练任务:</Typography.Text>{' '}
            <Tag color="blue">最优 trial</Tag>
          </div>
        </div>
      </Modal>
    </div>
  )
}
