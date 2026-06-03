import { useQuery } from '@tanstack/react-query'
import { useTenantStore } from '@/stores/tenantStore'
import { getTenantQuotaUsage } from '@/services/tenants'
import { parseK8sQuantity, formatKi } from '@/utils/format'

interface ResourceQuota {
  gpu: { used: number; total: number; percent: number; level: 'ok' | 'warning' | 'danger' }
  cpu: { used: number; total: number; percent: number; level: 'ok' | 'warning' | 'danger' }
  memory: { used: number; total: number; percent: number; level: 'ok' | 'warning' | 'danger' }
  storage: { used: number; total: number; percent: number; level: 'ok' | 'warning' | 'danger' }
}

function getLevel(percent: number): 'ok' | 'warning' | 'danger' {
  if (percent > 85) return 'danger'
  if (percent > 60) return 'warning'
  return 'ok'
}

export function useResourceQuota() {
  const currentTenant = useTenantStore((s) => s.currentTenant)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['tenantQuotaUsage', currentTenant?.id],
    queryFn: async () => {
      if (!currentTenant?.id) return null
      const res = await getTenantQuotaUsage(currentTenant.id)
      return res.data
    },
    enabled: !!currentTenant?.id,
    refetchInterval: 30_000,
  })

  const quota: ResourceQuota | null = (() => {
    if (!data || !currentTenant) return null

    const gpuUsed = data.gpuUsed ?? 0
    const gpuTotal = currentTenant.gpuLimit ?? 0
    const cpuUsed = parseK8sQuantity(data.cpuUsed)
    const cpuTotal = parseK8sQuantity(currentTenant.cpuLimit)
    const memUsedKi = parseK8sQuantity(data.memoryUsed)
    const memTotalKi = parseK8sQuantity(currentTenant.memoryLimit)
    const storUsedKi = parseK8sQuantity(data.storageUsed)
    const storTotalKi = parseK8sQuantity(currentTenant.storageLimit)

    return {
      gpu: {
        used: gpuUsed,
        total: gpuTotal,
        percent: gpuTotal ? (gpuUsed / gpuTotal) * 100 : 0,
        level: getLevel(gpuTotal ? (gpuUsed / gpuTotal) * 100 : 0),
      },
      cpu: {
        used: Math.round(cpuUsed),
        total: Math.round(cpuTotal),
        percent: cpuTotal ? (cpuUsed / cpuTotal) * 100 : 0,
        level: getLevel(cpuTotal ? (cpuUsed / cpuTotal) * 100 : 0),
      },
      memory: {
        used: memUsedKi,
        total: memTotalKi,
        percent: memTotalKi ? (memUsedKi / memTotalKi) * 100 : 0,
        level: getLevel(memTotalKi ? (memUsedKi / memTotalKi) * 100 : 0),
      },
      storage: {
        used: storUsedKi,
        total: storTotalKi,
        percent: storTotalKi ? (storUsedKi / storTotalKi) * 100 : 0,
        level: getLevel(storTotalKi ? (storUsedKi / storTotalKi) * 100 : 0),
      },
    }
  })()

  return { quota, isLoading, refetch, formatKi }
}
