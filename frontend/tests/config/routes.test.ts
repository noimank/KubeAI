import { describe, it, expect } from 'vitest'
import { getRoutePermission, ROUTE_PERMISSIONS } from '@/config/routes'

describe('routes config', () => {
  it('should have permission for protected routes', () => {
    expect(getRoutePermission('/training-jobs')).toBe('training_jobs:read')
    expect(getRoutePermission('/admin/tenants')).toBe('tenants:manage')
    expect(getRoutePermission('/admin/users')).toBe('users:manage')
    expect(getRoutePermission('/admin/audit-logs')).toBe('audit_logs:read')
  })

  it('should return undefined for dashboard (no permission needed)', () => {
    expect(getRoutePermission('/dashboard')).toBeUndefined()
  })

  it('should return undefined for unknown routes', () => {
    expect(getRoutePermission('/unknown')).toBeUndefined()
  })

  it('every entry has a path', () => {
    ROUTE_PERMISSIONS.forEach((r) => {
      expect(r.path).toBeTruthy()
    })
  })
})
