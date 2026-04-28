import { describe, it, expect, beforeEach } from 'vitest'
import { useRbacStore } from '@/stores/rbacStore'

describe('rbacStore', () => {
  beforeEach(() => {
    useRbacStore.getState().clearRbac()
  })

  it('should start with no role', () => {
    const state = useRbacStore.getState()
    expect(state.currentRole).toBeNull()
    expect(state.permissions).toEqual([])
  })

  it('should set admin with wildcard permission', () => {
    useRbacStore.getState().setRole('admin')
    const state = useRbacStore.getState()
    expect(state.currentRole).toBe('admin')
    expect(state.permissions).toContain('*')
  })

  it('admin should have all permissions via wildcard', () => {
    useRbacStore.getState().setRole('admin')
    expect(useRbacStore.getState().hasPermission('any:permission')).toBe(true)
  })

  it('annotator should have read/write annotations and read datasets', () => {
    useRbacStore.getState().setRole('annotator')
    const state = useRbacStore.getState()
    expect(state.hasPermission('datasets:read')).toBe(true)
    expect(state.hasPermission('annotations:read')).toBe(true)
    expect(state.hasPermission('annotations:write')).toBe(true)
    expect(state.hasPermission('training_jobs:write')).toBe(false)
  })

  it('engineer should have training job write access but not manage', () => {
    useRbacStore.getState().setRole('engineer')
    const state = useRbacStore.getState()
    expect(state.hasPermission('training_jobs:write')).toBe(true)
    expect(state.hasPermission('training_jobs:read')).toBe(true)
    expect(state.hasPermission('inference_services:read')).toBe(true)
    expect(state.hasPermission('inference_services:write')).toBe(false)
    expect(state.hasPermission('users:read')).toBe(false)
  })

  it('mlops should have manage on training jobs and read on users', () => {
    useRbacStore.getState().setRole('mlops')
    const state = useRbacStore.getState()
    expect(state.hasPermission('training_jobs:manage')).toBe(true)
    expect(state.hasPermission('training_jobs:write')).toBe(true)
    expect(state.hasPermission('users:read')).toBe(true)
    expect(state.hasPermission('users:manage')).toBe(false)
    expect(state.hasPermission('tenants:manage')).toBe(false)
  })

  it('should clear rbac state', () => {
    useRbacStore.getState().setRole('admin')
    useRbacStore.getState().clearRbac()
    const state = useRbacStore.getState()
    expect(state.currentRole).toBeNull()
    expect(state.permissions).toEqual([])
  })
})
