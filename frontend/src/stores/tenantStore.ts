import { create } from 'zustand'
import type { Tenant } from '@/types/tenant'
import { api } from '@/services/api'

interface TenantState {
  currentTenant: Tenant | null
  tenantList: Tenant[]
  loading: boolean
  setCurrentTenant: (tenant: Tenant) => void
  setTenantList: (tenants: Tenant[]) => void
  clearTenant: () => void
  fetchCurrentTenant: () => Promise<void>
}

export const useTenantStore = create<TenantState>((set) => ({
  currentTenant: null,
  tenantList: [],
  loading: false,

  setCurrentTenant: (tenant) => set({ currentTenant: tenant }),
  setTenantList: (tenants) => set({ tenantList: tenants }),
  clearTenant: () => set({ currentTenant: null, tenantList: [] }),

  fetchCurrentTenant: async () => {
    set({ loading: true })
    try {
      const res = await api.get('/tenants/me')
      if (res.data?.success && res.data.data) {
        set({ currentTenant: res.data.data })
      }
    } catch {
      // tenant may not exist yet for this user
    } finally {
      set({ loading: false })
    }
  },
}))
