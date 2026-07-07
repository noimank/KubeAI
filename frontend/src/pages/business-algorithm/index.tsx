import { Card, Button } from 'antd'
import { useNavigate } from 'react-router-dom'
import { ThunderboltOutlined, CalculatorOutlined, BuildOutlined } from '@ant-design/icons'

const categories = [
  {
    key: 'metaheuristic',
    title: '元启发算法',
    description: '模拟自然选择和群体智能的搜索优化算法，包括遗传算法、粒子群、免疫遗传、量子进化等',
    icon: <ThunderboltOutlined />,
    color: '#1677FF',
    bgColor: '#E6F4FF',
  },
  {
    key: 'data-planning',
    title: '数据规划算法',
    description: '基于数学规划的精确优化方法，包括混合整数规划、约束规划、拉格朗日松弛法等',
    icon: <CalculatorOutlined />,
    color: '#52C41A',
    bgColor: '#F6FFED',
  },
  {
    key: 'heuristic-rules',
    title: '启发式规则算法',
    description: '基于调度规则的快速启发式方法，包括转移瓶颈、插入规则、优先分派规则等',
    icon: <BuildOutlined />,
    color: '#FA8C16',
    bgColor: '#FFF7E6',
  },
]

export default function BusinessAlgorithmPage() {
  const navigate = useNavigate()

  return (
    <div style={{ padding: 24 }}>
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>业务算法库</h1>
        <p style={{ fontSize: 15, color: 'var(--ant-color-text-secondary)' }}>
          面向生产调度与资源优化的经典算法集合
        </p>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 24,
          maxWidth: 1200,
          margin: '0 auto',
        }}
      >
        {categories.map((cat) => (
          <Card
            key={cat.key}
            hoverable
            styles={{ body: { padding: 32 } }}
            onClick={() => navigate(`/business-algorithm/${cat.key}`)}
          >
            <div style={{ textAlign: 'center' }}>
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: '50%',
                  backgroundColor: cat.bgColor,
                  color: cat.color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 28,
                  margin: '0 auto 20px',
                }}
              >
                {cat.icon}
              </div>
              <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>{cat.title}</h3>
              <p
                style={{
                  fontSize: 14,
                  color: 'var(--ant-color-text-secondary)',
                  lineHeight: 1.6,
                  marginBottom: 20,
                  minHeight: 68,
                }}
              >
                {cat.description}
              </p>
              <Button type="primary">进入</Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
