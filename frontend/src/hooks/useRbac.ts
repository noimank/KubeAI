import { useRbacStore } from '@/stores/rbacStore'

export function useHasPermission(permission: string): boolean {
  return useRbacStore((state) => state.hasPermission(permission))
}
