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

  it('should set platform_admin with wildcard permission', () => {
    useRbacStore.getState().setRole('platform_admin')
    const state = useRbacStore.getState()
    expect(state.currentRole).toBe('platform_admin')
    expect(state.permissions).toContain('*')
  })

  it('should grant viewer only read permissions', () => {
    useRbacStore.getState().setRole('viewer')
    const state = useRbacStore.getState()
    expect(state.hasPermission('dataset:read')).toBe(true)
    expect(state.hasPermission('dataset:write')).toBe(false)
  })

  it('platform_admin should have all permissions via wildcard', () => {
    useRbacStore.getState().setRole('platform_admin')
    expect(useRbacStore.getState().hasPermission('any:permission')).toBe(true)
  })

  it('developer should have write access to datasets', () => {
    useRbacStore.getState().setRole('developer')
    const state = useRbacStore.getState()
    expect(state.hasPermission('dataset:write')).toBe(true)
    expect(state.hasPermission('tenant:write')).toBe(false)
  })
})
