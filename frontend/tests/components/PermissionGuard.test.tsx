import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PermissionGuard from '@/components/PermissionGuard'
import { useRbacStore } from '@/stores/rbacStore'

describe('PermissionGuard', () => {
  beforeEach(() => {
    useRbacStore.getState().clearRbac()
  })

  it('should render children when user has permission', () => {
    useRbacStore.getState().setRole('admin')
    const { getByText } = render(
      <MemoryRouter>
        <PermissionGuard permission="training_jobs:read">
          <div>Protected Content</div>
        </PermissionGuard>
      </MemoryRouter>,
    )

    expect(getByText('Protected Content')).toBeTruthy()
  })

  it('should redirect to 403 when user lacks permission', () => {
    useRbacStore.getState().setRole('annotator')
    const { queryByText } = render(
      <MemoryRouter>
        <PermissionGuard permission="training_jobs:read">
          <div>Protected Content</div>
        </PermissionGuard>
      </MemoryRouter>,
    )

    expect(queryByText('Protected Content')).toBeNull()
  })

  it('should allow annotator to access annotations', () => {
    useRbacStore.getState().setRole('annotator')
    const { getByText } = render(
      <MemoryRouter>
        <PermissionGuard permission="annotations:read">
          <div>Annotations Page</div>
        </PermissionGuard>
      </MemoryRouter>,
    )

    expect(getByText('Annotations Page')).toBeTruthy()
  })
})
