export const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending: { label: '初始化中', color: 'blue' },
  active: { label: '活跃', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
  archived: { label: '已归档', color: 'warning' },
}
