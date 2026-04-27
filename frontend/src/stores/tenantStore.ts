import { create } from 'zustand'
import type { Tenant } from '@/types/tenant'

interface TenantState {
  currentTenant: Tenant | null
  tenantList: Tenant[]
  setCurrentTenant: (tenant: Tenant) => void
  setTenantList: (tenants: Tenant[]) => void
  clearTenant: () => void
}

export const useTenantStore = create<TenantState>((set) => ({
  currentTenant: null,
  tenantList: [],

  setCurrentTenant: (tenant) => set({ currentTenant: tenant }),
  setTenantList: (tenants) => set({ tenantList: tenants }),
  clearTenant: () => set({ currentTenant: null, tenantList: [] }),
}))
