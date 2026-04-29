import { describe, it, expect } from 'vitest'
import { getStatusConfig } from '@/utils/statusColors'

describe('statusColors', () => {
  it('running 状态返回蓝色 processing 配置', () => {
    const config = getStatusConfig('running')
    expect(config.tagColor).toBe('processing')
    expect(config.label).toBe('运行中')
    expect(config.color).toBe('var(--status-running)')
  })

  it('succeeded 状态返回绿色 success 配置', () => {
    const config = getStatusConfig('succeeded')
    expect(config.tagColor).toBe('success')
    expect(config.label).toBe('成功')
    expect(config.color).toBe('var(--status-success)')
  })

  it('failed 状态返回红色 error 配置', () => {
    const config = getStatusConfig('failed')
    expect(config.tagColor).toBe('error')
    expect(config.label).toBe('失败')
    expect(config.color).toBe('var(--status-failed)')
  })

  it('queued 状态返回黄色 warning 配置', () => {
    const config = getStatusConfig('queued')
    expect(config.tagColor).toBe('warning')
    expect(config.label).toBe('排队中')
    expect(config.color).toBe('var(--status-queued)')
  })

  it('stopped 状态返回灰色 default 配置', () => {
    const config = getStatusConfig('stopped')
    expect(config.tagColor).toBe('default')
    expect(config.label).toBe('已停止')
    expect(config.color).toBe('var(--status-stopped)')
  })

  it('disabled 状态返回灰色 default 配置', () => {
    const config = getStatusConfig('disabled')
    expect(config.tagColor).toBe('default')
    expect(config.label).toBe('已禁用')
  })

  it('pending 状态返回黄色 warning 配置', () => {
    const config = getStatusConfig('pending')
    expect(config.tagColor).toBe('warning')
    expect(config.label).toBe('等待中')
  })

  it('未知状态返回 default 配置', () => {
    const config = getStatusConfig('nonexistent')
    expect(config.tagColor).toBe('default')
    expect(config.label).toBe('未知')
  })

  it('状态不区分大小写', () => {
    const config = getStatusConfig('RUNNING')
    expect(config.tagColor).toBe('processing')
    expect(config.label).toBe('运行中')
  })

  it('每个状态都有 icon', () => {
    const statuses = ['running', 'succeeded', 'failed', 'queued', 'stopped', 'disabled', 'pending']
    for (const status of statuses) {
      const config = getStatusConfig(status)
      expect(config.icon).toBeDefined()
    }
  })
})
