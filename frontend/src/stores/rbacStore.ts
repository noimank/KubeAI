import { create } from 'zustand'

export type Role = 'admin' | 'mlops' | 'engineer' | 'annotator'

interface RbacState {
  currentRole: Role | null
  permissions: string[]
  setRole: (role: Role) => void
  hasPermission: (permission: string) => boolean
  clearRbac: () => void
}

/**
 * 每个角色只定义自身的权限（不含继承）。
 * 与后端 SEED_ROLE_INHERITANCE 保持一致：
 *   admin → mlops → engineer → annotator
 */
const ROLE_OWN_PERMISSIONS: Record<Role, string[]> = {
  admin: ['*'], // 管理员通配，无需走继承链
  mlops: [
    'datasets:write',
    'annotations:manage',
    'training_jobs:manage',
    'experiments:manage',
    'models:write',
    'inference_services:write',
    'inference_services:manage',
    'dev_environments:manage',
    'dev_environment_images:manage',
    'monitoring:read',
    'audit_logs:read',
    'users:read',
    'algorithms:manage',
  ],
  engineer: [
    'training_jobs:read',
    'training_jobs:write',
    'experiments:read',
    'experiments:write',
    'models:read',
    'images:read',
    'images:build',
    'dev_environments:read',
    'dev_environments:write',
    'dev_environment_images:read',
    'inference_services:read',
    'algorithms:read',
    'algorithms:write',
  ],
  annotator: [
    'datasets:read',
    'annotations:read',
    'annotations:write',
    'notifications:read',
    'notifications:write',
  ],
}

/**
 * 继承链：(parent, child) 表示 parent 继承 child 的所有权限。
 * 与后端 SEED_ROLE_INHERITANCE 语义一致。
 */
const ROLE_INHERITANCE: Record<Role, Role[]> = {
  annotator: [],
  engineer: ['annotator'],
  mlops: ['engineer', 'annotator'],
  admin: ['mlops', 'engineer', 'annotator'], // admin 有 ['*']，本行仅作文档用
}

/** 按继承链展开角色的完整权限列表 */
function resolvePermissions(role: Role): string[] {
  // admin 直接返回通配符
  if (role === 'admin') return ['*']

  const chain = [role, ...ROLE_INHERITANCE[role]]
  const merged = chain.flatMap((r) => ROLE_OWN_PERMISSIONS[r])
  return [...new Set(merged)]
}

export const useRbacStore = create<RbacState>((set, get) => ({
  currentRole: null,
  permissions: [],

  setRole: (role) => {
    set({ currentRole: role, permissions: resolvePermissions(role) })
  },

  hasPermission: (permission) => {
    const { permissions } = get()
    return permissions.includes('*') || permissions.includes(permission)
  },

  clearRbac: () => set({ currentRole: null, permissions: [] }),
}))
