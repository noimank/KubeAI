import { Button, Progress, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'

interface TaskNavigatorProps {
  currentTaskIndex: number
  totalTasks: number
  completedTasks: number
  onPrev: () => void
  onNext: () => void
  hasPrev: boolean
  hasNext: boolean
}

export default function TaskNavigator({
  currentTaskIndex,
  totalTasks,
  completedTasks,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
}: TaskNavigatorProps) {
  const percent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0

  return (
    <div
      style={{
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        borderBottom: '1px solid var(--ant-color-border)',
      }}
    >
      <Progress percent={percent} size="small" format={() => `${completedTasks}/${totalTasks}`} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Button size="small" icon={<LeftOutlined />} disabled={!hasPrev} onClick={onPrev}>
          上一个
        </Button>
        <Typography.Text>
          {currentTaskIndex + 1} / {totalTasks}
        </Typography.Text>
        <Button size="small" disabled={!hasNext} onClick={onNext}>
          下一个 <RightOutlined />
        </Button>
      </div>
    </div>
  )
}
