import { create } from 'zustand'

type Role = 'platform_admin' | 'tenant_admin' | 'developer' | 'viewer'

interface RbacState {
  currentRole: Role | null
  permissions: string[]
  setRole: (role: Role) => void
  setPermissions: (permissions: string[]) => void
  hasPermission: (permission: string) => boolean
  clearRbac: () => void
}

const ROLE_PERMISSIONS: Record<Role, string[]> = {
  platform_admin: ['*'],
  tenant_admin: [
    'tenant:read',
    'tenant:write',
    'member:read',
    'member:write',
    'dataset:read',
    'dataset:write',
    'training:read',
    'training:write',
    'model:read',
    'model:write',
    'inference:read',
    'inference:write',
    'monitoring:read',
  ],
  developer: [
    'dataset:read',
    'dataset:write',
    'training:read',
    'training:write',
    'model:read',
    'model:write',
    'inference:read',
    'inference:write',
    'monitoring:read',
  ],
  viewer: ['dataset:read', 'training:read', 'model:read', 'inference:read', 'monitoring:read'],
}

export const useRbacStore = create<RbacState>((set, get) => ({
  currentRole: null,
  permissions: [],

  setRole: (role) => {
    set({ currentRole: role, permissions: ROLE_PERMISSIONS[role] })
  },

  setPermissions: (permissions) => set({ permissions }),

  hasPermission: (permission) => {
    const { permissions } = get()
    return permissions.includes('*') || permissions.includes(permission)
  },

  clearRbac: () => set({ currentRole: null, permissions: [] }),
}))
