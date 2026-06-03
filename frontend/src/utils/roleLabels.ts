/** 角色 → 中文标签 */
export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  mlops: 'MLOps 工程师',
  engineer: '算法工程师',
  annotator: '标注员',
}

/** 角色 → Tag 颜色 */
export const ROLE_COLORS: Record<string, string> = {
  admin: 'red',
  mlops: 'blue',
  engineer: 'green',
  annotator: 'orange',
}

/** 角色下拉选项（管理员角色通常不出现在邀请/分配选项中） */
export const ROLE_OPTIONS = [
  { label: '算法工程师', value: 'engineer' },
  { label: 'MLOps 工程师', value: 'mlops' },
  { label: '标注员', value: 'annotator' },
]

/** 角色下拉选项（含管理员，用于用户管理页等完整场景） */
export const ROLE_OPTIONS_WITH_ADMIN = [
  { label: '管理员', value: 'admin' },
  { label: 'MLOps 工程师', value: 'mlops' },
  { label: '算法工程师', value: 'engineer' },
  { label: '标注员', value: 'annotator' },
]
