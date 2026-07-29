export interface RoutePermission {
  path: string
  permission?: string
}

export const ROUTE_PERMISSIONS: RoutePermission[] = [
  { path: '/dashboard' },
  { path: '/datasets', permission: 'datasets:read' },
  { path: '/datasets/:id', permission: 'datasets:read' },
  { path: '/training-jobs', permission: 'training_jobs:read' },
  { path: '/experiments', permission: 'experiments:read' },
  { path: '/models', permission: 'models:read' },
  { path: '/inference', permission: 'inference_services:read' },
  { path: '/dev-environments', permission: 'dev_environments:read' },
  { path: '/images', permission: 'images:read' },
  { path: '/annotations', permission: 'annotations:read' },
  { path: '/data-explore', permission: 'data_explore:read' },
  { path: '/business-configs', permission: 'business_configs:read' },
  { path: '/monitoring', permission: 'monitoring:read' },
  { path: '/admin/tenants', permission: 'tenants:manage' },
  { path: '/admin/users', permission: 'users:manage' },
  { path: '/admin/audit-logs', permission: 'audit_logs:read' },
]

export function getRoutePermission(pathname: string): string | undefined {
  const match = ROUTE_PERMISSIONS.find((r) => r.path === pathname)
  return match?.permission
}
