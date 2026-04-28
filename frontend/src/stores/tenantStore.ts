import { create } from 'zustand'
import type { Tenant } from '@/types/tenant'

interface TenantState {
  currentTenant: Tenant | null
  tenantList: Tenant[]
  loading: boolean
  setCurrentTenant: (tenant: Tenant) => void
  setTenantList: (tenants: Tenant[]) => void
  clearTenant: () => void
  fetchCurrentTenant: () => Promise<void>
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

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
      const axios = (await import('axios')).default
      const token = localStorage.getItem('kubeai_access_token')
      const res = await axios.get(`${API_BASE}/tenants/me`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
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
