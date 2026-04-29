import {
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export type StatusCode =
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'queued'
  | 'stopped'
  | 'disabled'
  | 'pending'
  | 'unknown'

export interface StatusConfig {
  color: string
  tagColor: string
  icon: ReactNode
  label: string
}

const STATUS_MAP: Record<StatusCode, StatusConfig> = {
  running: {
    color: 'var(--status-running)',
    tagColor: 'processing',
    icon: <LoadingOutlined />,
    label: '运行中',
  },
  succeeded: {
    color: 'var(--status-success)',
    tagColor: 'success',
    icon: <CheckCircleOutlined />,
    label: '成功',
  },
  failed: {
    color: 'var(--status-failed)',
    tagColor: 'error',
    icon: <CloseCircleOutlined />,
    label: '失败',
  },
  queued: {
    color: 'var(--status-queued)',
    tagColor: 'warning',
    icon: <ClockCircleOutlined />,
    label: '排队中',
  },
  stopped: {
    color: 'var(--status-stopped)',
    tagColor: 'default',
    icon: <StopOutlined />,
    label: '已停止',
  },
  disabled: {
    color: 'var(--status-stopped)',
    tagColor: 'default',
    icon: <PauseCircleOutlined />,
    label: '已禁用',
  },
  pending: {
    color: 'var(--status-queued)',
    tagColor: 'warning',
    icon: <ClockCircleOutlined />,
    label: '等待中',
  },
  unknown: {
    color: 'var(--status-stopped)',
    tagColor: 'default',
    icon: <PauseCircleOutlined />,
    label: '未知',
  },
}

export function getStatusConfig(status: string): StatusConfig {
  return STATUS_MAP[status.toLowerCase() as StatusCode] ?? STATUS_MAP.unknown
}
