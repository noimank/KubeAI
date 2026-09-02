import { useState, useMemo, useRef, useEffect } from 'react'
import { Card, Button, Input, InputNumber, Select, Table, Progress } from 'antd'
import { getMessageInstance } from '@/utils/messageHolder'
import {
  DeleteOutlined,
  PlusOutlined,
  SettingOutlined,
  UnorderedListOutlined,
  FunctionOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'
import GanttChart from './components/GanttChart'
import { optimizeHr } from '@/services/businessAlgorithm'

const algorithms = [
  {
    code: 'SHIFTING_BOTTLENECK',
    name: '转移瓶颈基于差异的启发式',
    description: '通过识别和优化生产瓶颈来改进调度方案的启发式算法，能够有效平衡各工序负荷',
  },
  {
    code: 'INSERTION_RULES',
    name: 'CDS&NEH&Palmer基于插入的规则',
    description: '集合了CDS、NEH和Palmer三种经典插入式排序规则的调度方法，适用于流水车间调度问题',
  },
  {
    code: 'DISPATCHING_RULES',
    name: 'SPT&LPT&EDD优先分派规则',
    description: '包含最短加工时间(SPT)、最长加工时间(LPT)和最早截止日期(EDD)的优先分派规则集合',
  },
]

const priorityRules = [
  { label: 'CDS-Campbell-Dudek-Smith', value: 'CDS', algorithmCode: 'INSERTION_RULES' },
  { label: 'NEH-Nawaz-Enscore-Ham', value: 'NEH', algorithmCode: 'INSERTION_RULES' },
  { label: 'Palmer-Palmer启发式', value: 'Palmer', algorithmCode: 'INSERTION_RULES' },
  { label: 'SPT-最短处理时间优先', value: 'SPT', algorithmCode: 'DISPATCHING_RULES' },
  { label: 'LPT-最长处理时间优先', value: 'LPT', algorithmCode: 'DISPATCHING_RULES' },
  { label: 'EDD-最早交货期优先', value: 'EDD', algorithmCode: 'DISPATCHING_RULES' },
  { label: 'BF-转移瓶颈算法', value: 'BF', algorithmCode: 'SHIFTING_BOTTLENECK' },
]

interface ProcessItem {
  id: number
  name: string
  count: number | null
}

interface JobProcess {
  deviceId: number | null
  time: number | null
}

interface JobItem {
  id: number
  processes: JobProcess[]
}

interface OptimizationResult {
  algorithm: { name: string; time: string }
  result: { makespan: number }
  solutionInfo: {
    jobId: number
    operations: {
      id: number
      device: string
      startTime: number
      endTime: number
      duration: number
    }[]
  }[]
  deviceUtilization: { device: string; totalTime: number; utilizationRate: number }[]
}

export default function HeuristicRulesPage() {
  const [searchParams] = useSearchParams()
  const code = searchParams.get('code')

  const [view, setView] = useState<'list' | 'form' | 'result'>(code ? 'form' : 'list')
  const [selectedAlgorithm, setSelectedAlgorithm] = useState(() => {
    if (code) return algorithms.find((a) => a.code === code) || null
    return null
  })

  const nextProcessId = useRef(2)
  const nextJobId = useRef(2)
  const [processList, setProcessList] = useState<ProcessItem[]>([{ id: 1, name: '', count: null }])
  const [jobList, setJobList] = useState<JobItem[]>([
    { id: 1, processes: [{ deviceId: null, time: null }] },
  ])
  const [priorityRule, setPriorityRule] = useState('')
  const [maxIter, setMaxIter] = useState(10)
  const [dueDates, setDueDates] = useState<number[]>([0])

  const [loading, setLoading] = useState(false)
  const [resultData, setResultData] = useState<OptimizationResult | null>(null)

  const validProcessList = useMemo(
    () => processList.filter((p) => p.name && p.name.trim() !== ''),
    [processList],
  )

  const availableRules = useMemo(
    () => priorityRules.filter((r) => r.algorithmCode === selectedAlgorithm?.code),
    [selectedAlgorithm],
  )

  useEffect(() => {
    if (selectedAlgorithm) {
      const firstRule = priorityRules.find((r) => r.algorithmCode === selectedAlgorithm.code)
      if (firstRule) setPriorityRule(firstRule.value)
    }
  }, [selectedAlgorithm])

  const handleSelectAlgorithm = (algo: (typeof algorithms)[0]) => {
    setSelectedAlgorithm(algo)
    setView('form')
  }

  const addProcess = () => {
    setProcessList([...processList, { id: nextProcessId.current, name: '', count: null }])
    nextProcessId.current++
  }
  const removeProcess = (index: number) => {
    const newList = [...processList]
    const removed = newList.splice(index, 1)[0]
    setProcessList(newList)
    setJobList(
      jobList.map((job) => ({
        ...job,
        processes: job.processes.filter((p) => !p.deviceId || p.deviceId !== removed?.id),
      })),
    )
  }
  const updateProcess = (index: number, field: keyof ProcessItem, value: unknown) => {
    const newList = [...processList]
    newList[index] = { ...newList[index], [field]: value }
    setProcessList(newList)
  }

  const addJob = () => {
    setJobList([...jobList, { id: nextJobId.current, processes: [{ deviceId: null, time: null }] }])
    setDueDates([...dueDates, 0])
    nextJobId.current++
  }
  const removeJob = (index: number) => {
    setJobList(jobList.filter((_, i) => i !== index))
    setDueDates(dueDates.filter((_, i) => i !== index))
  }
  const addJobProcess = (jobIndex: number) => {
    const job = jobList[jobIndex]
    const usedIds = job.processes.map((p) => p.deviceId).filter(Boolean) as number[]
    const available = validProcessList.filter((p) => !usedIds.includes(p.id))
    if (available.length === 0) {
      getMessageInstance()?.warning('该作业已包含所有有效工序')
      return
    }
    const newList = [...jobList]
    newList[jobIndex] = { ...job, processes: [...job.processes, { deviceId: null, time: null }] }
    setJobList(newList)
  }
  const removeJobProcess = (jobIndex: number, processIndex: number) => {
    const newList = [...jobList]
    const job = newList[jobIndex]
    newList[jobIndex] = { ...job, processes: job.processes.filter((_, i) => i !== processIndex) }
    setJobList(newList)
  }
  const updateJobProcess = (
    jobIndex: number,
    processIndex: number,
    field: keyof JobProcess,
    value: unknown,
  ) => {
    const newList = [...jobList]
    const job = newList[jobIndex]
    const processes = [...job.processes]
    processes[processIndex] = { ...processes[processIndex], [field]: value }
    newList[jobIndex] = { ...job, processes }
    setJobList(newList)
  }

  const getAvailableProcesses = (job: JobItem, currentIndex: number) => {
    const selectedIds = job.processes
      .filter((_, i) => i !== currentIndex)
      .map((p) => p.deviceId)
      .filter(Boolean) as number[]
    return validProcessList.filter((p) => !selectedIds.includes(p.id))
  }

  const validateForm = (): string | null => {
    for (const p of processList) {
      if (p.name && p.name.trim() !== '' && (!p.count || p.count < 1)) {
        return `工序"${p.name}"的设备数量必须大于0`
      }
    }
    if (validProcessList.length === 0) return '请至少填写一个工序的名称和设备数量'
    for (const job of jobList) {
      for (const p of job.processes) {
        if (!p.deviceId) return '请选择所有作业工序'
        if (!p.time || p.time <= 0) return '请确保所有工序时间大于0'
      }
      const ids = job.processes.map((p) => p.deviceId)
      if (new Set(ids).size !== ids.length) return '作业中的工序不能重复'
    }
    if (!priorityRule) return '请选择优先规则'
    if (priorityRule === 'BF' && (!maxIter || maxIter < 1))
      return '请输入有效的迭代轮次（必须大于0）'
    if (priorityRule === 'EDD') {
      for (let i = 0; i < dueDates.length; i++) {
        if (!dueDates[i] || dueDates[i] <= 0) return `作业${i + 1}的交付日期必须大于0`
      }
    }
    return null
  }

  const handleSubmit = () => {
    const error = validateForm()
    if (error) {
      getMessageInstance()?.error(error)
      return
    }
    setLoading(true)
    const submitData = {
      algorithm: {
        name: priorityRule,
        objective: 'makespan',
        maxIter: priorityRule === 'BF' ? maxIter : null,
      },
      devices: processList,
      jobs: jobList,
      dueDates: priorityRule === 'EDD' ? dueDates : [],
    }
    optimizeHr(submitData)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((res: any) => {
        setResultData(res.data || res)
        setView('result')
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .catch((err: any) => {
        getMessageInstance()?.error(err?.response?.data?.error || err?.message || '优化请求失败')
      })
      .finally(() => setLoading(false))
  }

  if (view === 'list') {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>启发式规则算法</h1>
          <p style={{ fontSize: 15, color: 'var(--ant-color-text-secondary)' }}>
            通过启发式规则对操纵对象进行参数优化
          </p>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 20,
            maxWidth: 1200,
            margin: '0 auto',
          }}
        >
          {algorithms.map((algo) => (
            <Card
              key={algo.code}
              hoverable
              styles={{ body: { textAlign: 'center', padding: 24 } }}
              onClick={() => handleSelectAlgorithm(algo)}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  backgroundColor: '#FFF7E6',
                  borderRadius: '50%',
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  margin: '0 auto 16px',
                  fontSize: 22,
                  color: '#FA8C16',
                }}
              >
                <FunctionOutlined />
              </div>
              <h3 style={{ fontSize: 17, fontWeight: 600, marginBottom: 8 }}>{algo.name}</h3>
              <p
                style={{
                  fontSize: 13,
                  color: 'var(--ant-color-text-secondary)',
                  lineHeight: 1.5,
                  marginBottom: 16,
                  minHeight: 58,
                }}
              >
                {algo.description}
              </p>
              <Button type="primary" size="small">
                选择
              </Button>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  if (view === 'result' && resultData) {
    const { algorithm, result, solutionInfo, deviceUtilization } = resultData
    return (
      <div style={{ padding: 24 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <h1 style={{ fontSize: 24, fontWeight: 600 }}>调度结果展示</h1>
        </div>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-around',
            marginBottom: 24,
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          {[
            { label: '算法', value: algorithm?.name || '-' },
            { label: '最大完工时间', value: result?.makespan ?? '-' },
            { label: '计算时间(秒)', value: algorithm?.time || '-' },
          ].map((item, i) => (
            <Card key={i} style={{ width: 200, textAlign: 'center' }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: '#1890FF', marginBottom: 8 }}>
                {item.value}
              </div>
              <div style={{ color: 'var(--ant-color-text-secondary)', fontSize: 14 }}>
                {item.label}
              </div>
            </Card>
          ))}
        </div>

        <Card style={{ marginBottom: 24 }} title="执行顺序">
          <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
            {(solutionInfo || []).map((task, i) => (
              <span key={task.jobId} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span
                  style={{
                    backgroundColor: '#1890FF',
                    color: '#fff',
                    padding: '6px 16px',
                    borderRadius: 20,
                    fontSize: 14,
                  }}
                >
                  作业{task.jobId}
                </span>
                {i < solutionInfo.length - 1 && (
                  <span style={{ color: '#1890FF', fontSize: 18 }}>&rarr;</span>
                )}
              </span>
            ))}
          </div>
        </Card>

        <Card style={{ marginBottom: 24 }} title="详细调度计划">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {(solutionInfo || []).map((task) => (
              <div
                key={task.jobId}
                style={{
                  border: '1px solid var(--ant-color-border)',
                  borderRadius: 6,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    backgroundColor: 'var(--ant-color-fill-tertiary)',
                    padding: '10px 16px',
                    fontWeight: 600,
                    borderBottom: '1px solid var(--ant-color-border)',
                  }}
                >
                  作业{task.jobId}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', padding: 16, gap: 12 }}>
                  {(task.operations || []).map((op) => (
                    <div
                      key={op.id}
                      style={{
                        backgroundColor: '#E6F4FF',
                        padding: '10px 18px',
                        borderRadius: 6,
                        minWidth: 180,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: '#1890FF', marginBottom: 4 }}>
                        {op.device}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--ant-color-text-secondary)' }}>
                        {op.startTime.toFixed(2)} - {op.endTime.toFixed(2)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card style={{ marginBottom: 24 }} title="甘特图">
          <GanttChart
            solutionInfo={solutionInfo || []}
            deviceUtilization={deviceUtilization || []}
          />
        </Card>

        <Card style={{ marginBottom: 24 }} title="机器利用率（流水车间调度）">
          {(deviceUtilization || []).map((util, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 14, marginBottom: 6 }}>
                {util.device} - 总使用时间: {util.totalTime?.toFixed(2)}, 利用率:{' '}
                {(util.utilizationRate * 100).toFixed(2)}%
              </div>
              <Progress
                percent={Number((util.utilizationRate * 100).toFixed(2))}
                strokeColor="#52C41A"
              />
            </div>
          ))}
        </Card>

        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Button
            type="primary"
            size="large"
            onClick={() => {
              setView('form')
              setResultData(null)
            }}
          >
            重置
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>
          {selectedAlgorithm?.name}-工序作业配置表单
        </h1>
        <p style={{ color: 'var(--ant-color-text-secondary)', fontSize: 14 }}>
          先配置工序列表及数量，作业工序行数不能超过工序列表总数且不可重复
        </p>
      </div>

      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <Card
          style={{ marginBottom: 20 }}
          title={
            <span>
              <SettingOutlined style={{ marginRight: 8, color: '#1890FF' }} />
              工序列表配置
            </span>
          }
          extra={
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={addProcess}>
              添加工序
            </Button>
          }
        >
          <p style={{ marginBottom: 10 }}>当前工序数：{validProcessList.length}</p>
          <Table
            dataSource={processList}
            rowKey="id"
            pagination={false}
            size="small"
            columns={[
              {
                title: '工序名称',
                dataIndex: 'name',
                render: (_v: string, _record: ProcessItem, index: number) => (
                  <Input
                    value={processList[index].name}
                    placeholder="请输入工序名称"
                    onChange={(e) => updateProcess(index, 'name', e.target.value)}
                  />
                ),
              },
              {
                title: '设备数量',
                dataIndex: 'count',
                width: 200,
                render: (_v: number | null, _record: ProcessItem, index: number) => (
                  <InputNumber
                    min={1}
                    value={processList[index].count}
                    placeholder="请输入设备数量"
                    style={{ width: '100%' }}
                    onChange={(val) => updateProcess(index, 'count', val)}
                  />
                ),
              },
              {
                title: '操作',
                width: 80,
                render: (_v: unknown, _record: ProcessItem, index: number) =>
                  processList.length > 1 ? (
                    <Button
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => removeProcess(index)}
                    />
                  ) : null,
              },
            ]}
          />
          <div
            style={{
              fontSize: 13,
              padding: 10,
              backgroundColor: 'var(--ant-color-fill-tertiary)',
              borderRadius: 4,
              marginTop: 12,
              color: 'var(--ant-color-text-secondary)',
            }}
          >
            <InfoCircleOutlined style={{ marginRight: 5 }} />
            提示：添加所有可能用到的工序及对应设备数量，作业工序数量不能超过此处的工序总数
          </div>
        </Card>

        <Card
          style={{ marginBottom: 20 }}
          title={
            <span>
              <UnorderedListOutlined style={{ marginRight: 8, color: '#1890FF' }} />
              作业配置
            </span>
          }
          extra={
            <Button type="primary" size="small" icon={<PlusOutlined />} onClick={addJob}>
              添加作业
            </Button>
          }
        >
          {jobList.map((job, jobIndex) => (
            <div
              key={job.id}
              style={{
                marginBottom: 20,
                padding: 16,
                backgroundColor: 'var(--ant-color-fill-tertiary)',
                borderRadius: 4,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontWeight: 600, marginRight: 10 }}>作业{jobIndex + 1}</span>
                <span style={{ color: '#52C41A', fontSize: 14, marginRight: 'auto' }}>
                  已添加：{job.processes.filter((p) => p.deviceId).length}/{validProcessList.length}
                </span>
                {jobList.length > 1 && (
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => removeJob(jobIndex)}
                  />
                )}
              </div>
              {job.processes.map((proc, procIndex) => {
                const available = getAvailableProcesses(job, procIndex)
                return (
                  <div
                    key={procIndex}
                    style={{ display: 'flex', alignItems: 'center', marginBottom: 10, gap: 10 }}
                  >
                    <Select
                      value={proc.deviceId || undefined}
                      placeholder="选择工序"
                      style={{ width: 200 }}
                      onChange={(val) => updateJobProcess(jobIndex, procIndex, 'deviceId', val)}
                    >
                      {available.map((p) => (
                        <Select.Option key={p.id} value={p.id}>
                          {p.name}
                        </Select.Option>
                      ))}
                    </Select>
                    <InputNumber
                      value={proc.time}
                      min={0.1}
                      step={0.1}
                      placeholder="时间（小时）"
                      style={{ width: 200 }}
                      onChange={(val) => updateJobProcess(jobIndex, procIndex, 'time', val)}
                    />
                    {job.processes.length > 1 && (
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => removeJobProcess(jobIndex, procIndex)}
                      />
                    )}
                  </div>
                )
              })}
              <Button
                type="dashed"
                size="small"
                icon={<PlusOutlined />}
                disabled={job.processes.length >= validProcessList.length}
                onClick={() => addJobProcess(jobIndex)}
                style={{ marginTop: 8 }}
              >
                添加工序行
              </Button>
            </div>
          ))}
        </Card>

        <Card
          style={{ marginBottom: 20 }}
          title={
            <span>
              <FunctionOutlined style={{ marginRight: 8, color: '#1890FF' }} />
              算法参数配置
            </span>
          }
        >
          <div style={{ marginBottom: 20, display: 'flex', alignItems: 'center', gap: 16 }}>
            <span>优先规则：</span>
            <Select
              value={priorityRule || undefined}
              placeholder="选择优先级规则"
              style={{ width: 300 }}
              onChange={(val) => setPriorityRule(val)}
            >
              {availableRules.map((rule) => (
                <Select.Option key={rule.value} value={rule.value}>
                  {rule.label}
                </Select.Option>
              ))}
            </Select>
          </div>
          <div
            style={{
              color: 'var(--ant-color-text-tertiary)',
              fontSize: 12,
              marginTop: -12,
              marginBottom: 20,
            }}
          >
            选择作业排序的优先级规则算法
          </div>

          {priorityRule === 'BF' && (
            <div style={{ marginBottom: 16 }}>
              <span style={{ marginRight: 10 }}>迭代轮次：</span>
              <InputNumber
                value={maxIter}
                min={1}
                placeholder="请输入迭代轮次"
                onChange={(val) => setMaxIter(val || 10)}
              />
            </div>
          )}

          {priorityRule === 'EDD' && (
            <div
              style={{
                marginTop: 16,
                paddingTop: 16,
                borderTop: '1px dashed var(--ant-color-border)',
              }}
            >
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>交付日期配置</h3>
              {dueDates.map((date, index) => (
                <div key={index} style={{ marginBottom: 10 }}>
                  <span style={{ display: 'inline-block', width: 80 }}>作业{index + 1}:</span>
                  <InputNumber
                    value={date || undefined}
                    min={0.1}
                    step={0.1}
                    placeholder="交付日期（小时）"
                    style={{ width: 200 }}
                    onChange={(val) => {
                      const newDates = [...dueDates]
                      newDates[index] = val || 0
                      setDueDates(newDates)
                    }}
                  />
                  <span style={{ marginLeft: 5, color: 'var(--ant-color-text-tertiary)' }}>
                    小时
                  </span>
                </div>
              ))}
              <div style={{ color: 'var(--ant-color-text-tertiary)', fontSize: 12, marginTop: 8 }}>
                为每个作业输入对应的交付日期时间，用于EDD算法排序
              </div>
            </div>
          )}
        </Card>

        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Button type="primary" size="large" loading={loading} onClick={handleSubmit}>
            生成配置结果
          </Button>
        </div>
      </div>
    </div>
  )
}
