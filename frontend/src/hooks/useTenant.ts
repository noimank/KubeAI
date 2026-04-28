import { useTenantStore } from '@/stores/tenantStore'

export function useCurrentTenant() {
  const currentTenant = useTenantStore((s) => s.currentTenant)
  const loading = useTenantStore((s) => s.loading)
  const fetchCurrentTenant = useTenantStore((s) => s.fetchCurrentTenant)

  return {
    tenant: currentTenant,
    loading,
    fetchCurrentTenant,
    hasTenant: !!currentTenant,
  }
}
