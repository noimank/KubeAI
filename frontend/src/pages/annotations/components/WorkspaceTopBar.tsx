import { Button, Space, Tag, Tooltip } from 'antd'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import TaskNavigator from './TaskNavigator'

interface WorkspaceTopBarProps {
  projectName: string
  readOnly: boolean
  onBack: () => void
  cursor: number
  totalTasks: number
  completedTasks: number
  onPrev: () => void
  onNext: () => void
  hasPrev: boolean
  hasNext: boolean
  onHotkeyHelp: () => void
  guidelineCollapsed: boolean
  onToggleGuideline: () => void
}

/** 工作区顶栏 —— 返回/项目名/任务导航/快捷键/规范折叠 */
export default function WorkspaceTopBar({
  projectName,
  readOnly,
  onBack,
  cursor,
  totalTasks,
  completedTasks,
  onPrev,
  onNext,
  hasPrev,
  hasNext,
  onHotkeyHelp,
  guidelineCollapsed,
  onToggleGuideline,
}: WorkspaceTopBarProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 16px',
        borderBottom: '1px solid var(--ant-color-border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>
          返回
        </Button>
        <span style={{ fontWeight: 500 }}>{projectName}</span>
        {readOnly && <Tag color="green">已完成 - 只读</Tag>}
      </div>
      <Space>
        <TaskNavigator
          currentTaskIndex={cursor}
          totalTasks={totalTasks}
          completedTasks={completedTasks}
          onPrev={onPrev}
          onNext={onNext}
          hasPrev={hasPrev}
          hasNext={hasNext}
        />
        <Tooltip title="快捷键帮助">
          <Button type="text" icon={<QuestionCircleOutlined />} onClick={onHotkeyHelp} />
        </Tooltip>
      </Space>
      <Button type="text" onClick={onToggleGuideline}>
        规范 {guidelineCollapsed ? '▸' : '▾'}
      </Button>
    </div>
  )
}
