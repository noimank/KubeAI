import type { AuditAction, ResourceType } from '@/types/audit'

/** 操作类型 → 中文标签 */
export const ACTION_LABELS: Record<AuditAction, string> = {
  create: '创建',
  update: '更新',
  delete: '删除',
  login: '登录',
  logout: '登出',
  register: '注册',
  enable: '启用',
  disable: '禁用',
  invite: '邀请',
  accept_invite: '接受邀请',
  cancel_invite: '取消邀请',
  update_role: '变更角色',
  add_member: '添加成员',
  remove_member: '移除成员',
  update_quota: '调整配额',
  transfer_quota: '配额调配',
  upload: '上传',
  build: '构建',
  rebuild: '重新构建',
  cleanup_job: '清理任务',
  download: '下载',
}

/** 操作类型 → Tag 颜色 */
export const ACTION_COLORS: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  login: 'cyan',
  logout: 'default',
  register: 'purple',
  enable: 'green',
  disable: 'red',
  invite: 'blue',
  accept_invite: 'green',
  cancel_invite: 'orange',
  update_role: 'blue',
  add_member: 'green',
  remove_member: 'red',
  update_quota: 'geekblue',
  transfer_quota: 'purple',
  upload: 'green',
  build: 'geekblue',
  rebuild: 'orange',
  cleanup_job: 'default',
  download: 'cyan',
}

/** 资源类型 → 中文标签 */
export const RESOURCE_LABELS: Record<ResourceType, string> = {
  tenant: '租户',
  user: '用户',
  quota: '配额',
  membership: '成员关系',
  invitation: '邀请',
  credential: '凭证',
  dataset: '数据集',
  image: '镜像',
  dev_environment_image: '开发环境镜像',
  training_job: '训练任务',
  model: '模型',
  annotation_project: '标注项目',
  algorithm: '算法',
}

/** 资源类型 → Tag 颜色 */
export const RESOURCE_COLORS: Record<string, string> = {
  tenant: 'blue',
  user: 'purple',
  quota: 'orange',
  membership: 'cyan',
  invitation: 'green',
  credential: 'default',
  dataset: 'geekblue',
  image: 'cyan',
  dev_environment_image: 'lime',
  training_job: 'green',
  model: 'orange',
  annotation_project: 'magenta',
  algorithm: 'purple',
}

/** 操作类型下拉选项 */
export const ACTION_OPTIONS = Object.entries(ACTION_LABELS).map(([value, label]) => ({
  label,
  value,
}))

/** 资源类型下拉选项 */
export const RESOURCE_OPTIONS = Object.entries(RESOURCE_LABELS).map(([value, label]) => ({
  label,
  value,
}))
