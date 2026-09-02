import { useState } from 'react'
import { Card, Button } from 'antd'
import { getMessageInstance } from '@/utils/messageHolder'
import { useSearchParams } from 'react-router-dom'
import ResourceAllocationForm from './components/ResourceAllocationForm'
import ResourceAllocationResult, {
  type ResourceAllocationResultData,
} from './components/ResourceAllocationResult'
import { optimizeDp } from '@/services/businessAlgorithm'

const algorithms = [
  {
    code: 'MIP',
    name: '混合整数规划',
    description: '结合整数变量和连续变量的数学规划方法，广泛应用于资源分配和调度优化问题',
  },
  {
    code: 'CP',
    name: '约束规划',
    description: '通过系统地满足一组约束条件来求解组合优化问题的方法，特别适合复杂约束场景',
  },
  {
    code: 'LR',
    name: '拉格朗日松弛法',
    description: '将复杂约束问题转化为更容易处理的无约束问题的优化技术，有效降低问题复杂度',
  },
]

export default function DataPlanningPage() {
  const [searchParams] = useSearchParams()
  const code = searchParams.get('code')

  const [view, setView] = useState<'list' | 'form' | 'result'>(code ? 'form' : 'list')
  const [selectedAlgorithm, setSelectedAlgorithm] = useState(() => {
    if (code) {
      const found = algorithms.find((a) => a.code === code)
      return found || null
    }
    return null
  })
  const [loading, setLoading] = useState(false)
  const [resultData, setResultData] = useState<ResourceAllocationResultData | null>(null)

  const handleSelectAlgorithm = (algo: (typeof algorithms)[0]) => {
    setSelectedAlgorithm(algo)
    setView('form')
  }

  const handleSubmit = (formData: Record<string, unknown>) => {
    if (!selectedAlgorithm) return
    setLoading(true)
    const submitData = {
      totalDemand: formData.totalDemand,
      devices: formData.devices,
      manipulatedObjects: formData.manipulatedObjects,
      algorithm: {
        name: selectedAlgorithm.code,
        runtimePref: formData.runtimePref,
      },
    }
    optimizeDp(submitData)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then((res: any) => {
        const data = res.data || res
        setResultData({
          algorithm: data.algorithm,
          status: data.status,
          objective: data.objective,
          solutionInfo: data.solutionInfo || { devices: [], manipulatedObjects: [] },
        })
        setView('result')
      })
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .catch((err: any) => {
        getMessageInstance()?.error(err?.response?.data?.error || err?.message || '优化请求失败')
      })
      .finally(() => setLoading(false))
  }

  const handleReset = () => {
    setView('form')
    setResultData(null)
  }

  if (view === 'list') {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>数据规划算法</h1>
          <p style={{ fontSize: 15, color: 'var(--ant-color-text-secondary)' }}>
            通过数据规划算法对操纵对象进行参数优化
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
                  backgroundColor: '#F6FFED',
                  borderRadius: '50%',
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  margin: '0 auto 16px',
                  fontSize: 22,
                  color: '#52C41A',
                  fontWeight: 600,
                }}
              >
                {algo.code.charAt(0)}
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
    return <ResourceAllocationResult resultData={resultData} onReset={handleReset} />
  }

  return (
    <ResourceAllocationForm
      algorithmName={selectedAlgorithm?.name || ''}
      onSubmit={handleSubmit}
      onCancel={() => setView('list')}
      loading={loading}
    />
  )
}
