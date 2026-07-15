import { useState } from 'react'
import { Card, Button } from 'antd'
import { getMessageInstance } from '@/utils/messageHolder'
import { useSearchParams } from 'react-router-dom'
import ResourceAllocationForm from './components/ResourceAllocationForm'
import ResourceAllocationResult, {
  type ResourceAllocationResultData,
} from './components/ResourceAllocationResult'
import { optimizeHa } from '@/services/businessAlgorithm'

const algorithms = [
  {
    code: 'GA',
    name: '遗传算法',
    description:
      '模拟自然选择和遗传机制的搜索优化算法，通过选择、交叉、变异等操作不断进化种群以寻求最优解',
  },
  {
    code: 'PSO',
    name: '粒子群算法',
    description: '模拟鸟群觅食行为的群体智能优化算法，通过个体最优和群体最优的协同搜索实现全局优化',
  },
  {
    code: 'IGA',
    name: '免疫遗传算法',
    description: '融合免疫机制与遗传算法的混合优化方法，利用免疫记忆和抗体多样性提高搜索效率',
  },
  {
    code: 'QEA',
    name: '量子进化算法',
    description: '基于量子计算原理的进化算法，利用量子比特的叠加态和纠缠特性增强搜索能力',
  },
  {
    code: 'TS',
    name: '禁忌搜索',
    description: '通过禁忌表记录历史搜索路径以避免重复搜索的邻域搜索算法，适用于组合优化问题',
  },
  {
    code: 'VNS',
    name: '变领域搜索',
    description: '通过系统地改变邻域结构来跳出局部最优的元启发式算法，实现全局搜索空间的多样化探索',
  },
  {
    code: 'ENS',
    name: '完全领域搜索',
    description: '通过穷举当前解的所有邻域解来寻找最优改进方向的搜索算法',
  },
  {
    code: 'VDS',
    name: '变深度搜索',
    description: '结合深度搜索策略的局部搜索方法，通过逐步加深搜索深度来平衡搜索的广度和深度',
  },
]

export default function MetaheuristicPage() {
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
    optimizeHa(submitData)
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
          <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>元启发算法</h1>
          <p style={{ fontSize: 15, color: 'var(--ant-color-text-secondary)' }}>
            通过元启发算法对操纵对象进行参数优化
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
                  backgroundColor: '#E6F4FF',
                  borderRadius: '50%',
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  margin: '0 auto 16px',
                  fontSize: 22,
                  color: '#1677FF',
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
