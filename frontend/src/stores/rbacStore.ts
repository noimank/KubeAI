import { create } from 'zustand'

export type Role = 'admin' | 'mlops' | 'engineer' | 'annotator'

interface RbacState {
  currentRole: Role | null
  permissions: string[]
  setRole: (role: Role) => void
  hasPermission: (permission: string) => boolean
  clearRbac: () => void
}

const ROLE_PERMISSIONS: Record<Role, string[]> = {
  admin: ['*'],
  mlops: [
    'datasets:read',
    'datasets:write',
    'annotations:read',
    'annotations:write',
    'annotations:manage',
    'training_jobs:read',
    'training_jobs:write',
    'training_jobs:manage',
    'experiments:read',
    'experiments:write',
    'experiments:manage',
    'models:read',
    'models:write',
    'inference_services:read',
    'inference_services:write',
    'inference_services:manage',
    'images:read',
    'images:build',
    'dev_environments:read',
    'dev_environments:write',
    'dev_environments:manage',
    'dev_environment_images:read',
    'dev_environment_images:manage',
    'monitoring:read',
    'audit_logs:read',
    'users:read',
    'notifications:read',
    'notifications:write',
    'algorithms:read',
    'algorithms:write',
    'algorithms:manage',
  ],
  engineer: [
    'datasets:read',
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
    'notifications:read',
    'notifications:write',
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

export const useRbacStore = create<RbacState>((set, get) => ({
  currentRole: null,
  permissions: [],

  setRole: (role) => {
    set({ currentRole: role, permissions: ROLE_PERMISSIONS[role] })
  },

  hasPermission: (permission) => {
    const { permissions } = get()
    return permissions.includes('*') || permissions.includes(permission)
  },

  clearRbac: () => set({ currentRole: null, permissions: [] }),
}))
