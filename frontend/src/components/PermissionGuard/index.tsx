import { Navigate } from 'react-router-dom'
import { useRbacStore } from '@/stores/rbacStore'

interface PermissionGuardProps {
  permission: string
  children: React.ReactNode
}

export default function PermissionGuard({ permission, children }: PermissionGuardProps) {
  const hasPermission = useRbacStore((s) => s.hasPermission)

  if (!hasPermission(permission)) {
    return <Navigate to="/403" replace />
  }

  return <>{children}</>
}
