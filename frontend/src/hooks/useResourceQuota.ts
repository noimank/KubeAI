import { useQuery } from '@tanstack/react-query'
import { useTenantStore } from '@/stores/tenantStore'
import { getTenantQuotaUsage } from '@/services/tenants'

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

function parseK8sQuantity(val: string | undefined | null): number {
  if (!val) return 0
  if (val.endsWith('Gi')) return parseFloat(val) * 1024
  if (val.endsWith('Mi')) return parseFloat(val)
  if (val.endsWith('Ki')) return parseFloat(val) / 1024
  if (val.endsWith('G')) return parseFloat(val) * 1000
  if (val.endsWith('M')) return parseFloat(val)
  if (val.endsWith('m')) return parseFloat(val) / 1000
  return parseFloat(val) || 0
}

function formatMemoryMi(mi: number): string {
  if (mi >= 1024) return `${(mi / 1024).toFixed(1)} Gi`
  return `${mi} Mi`
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
    const memUsedMi = parseK8sQuantity(data.memoryUsed)
    const memTotalMi = parseK8sQuantity(currentTenant.memoryLimit)
    const storUsedMi = parseK8sQuantity(data.storageUsed)
    const storTotalMi = parseK8sQuantity(currentTenant.storageLimit)

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
        used: memUsedMi,
        total: memTotalMi,
        percent: memTotalMi ? (memUsedMi / memTotalMi) * 100 : 0,
        level: getLevel(memTotalMi ? (memUsedMi / memTotalMi) * 100 : 0),
      },
      storage: {
        used: storUsedMi,
        total: storTotalMi,
        percent: storTotalMi ? (storUsedMi / storTotalMi) * 100 : 0,
        level: getLevel(storTotalMi ? (storUsedMi / storTotalMi) * 100 : 0),
      },
    }
  })()

  return { quota, isLoading, refetch, formatMemoryMi }
}
