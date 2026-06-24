import { describe, it, expect, beforeEach } from 'vitest'
import { useRbacStore } from '@/stores/rbacStore'
import { filterMenuItems } from '@/layouts/components/sidebar-utils'
import type { MenuItem } from '@/layouts/components/sidebar-utils'
import { buildSidebarMenu } from '@/layouts/components/Sidebar'

describe('Sidebar role filtering', () => {
  beforeEach(() => {
    useRbacStore.getState().clearRbac()
  })

  it('admin sees all menus', () => {
    useRbacStore.getState().setRole('admin')
    const { hasPermission } = useRbacStore.getState()
    const items: MenuItem[] = [
      { path: '/dashboard', name: '工作台', icon: null },
      { path: '/training-jobs', name: '训练任务', icon: null, permission: 'training_jobs:read' },
      { path: '/admin/tenants', name: '租户管理', icon: null, permission: 'tenants:manage' },
    ]
    const filtered = filterMenuItems(items, hasPermission)
    expect(filtered).toHaveLength(3)
  })

  it('annotator sees only dashboard, datasets, annotations', () => {
    useRbacStore.getState().setRole('annotator')
    const { hasPermission } = useRbacStore.getState()
    const items: MenuItem[] = [
      { path: '/dashboard', name: '工作台', icon: null },
      { path: '/datasets', name: '数据集', icon: null, permission: 'datasets:read' },
      { path: '/training-jobs', name: '训练任务', icon: null, permission: 'training_jobs:read' },
      { path: '/annotations', name: '数据标注', icon: null, permission: 'annotations:read' },
      { path: '/monitoring', name: '监控', icon: null, permission: 'monitoring:read' },
    ]
    const filtered = filterMenuItems(items, hasPermission)
    const names = filtered.map((i) => i.name)
    expect(names).toEqual(['工作台', '数据集', '数据标注'])
  })

  it('engineer sees dev menus and inherited annotations, but not monitoring or admin', () => {
    useRbacStore.getState().setRole('engineer')
    const { hasPermission } = useRbacStore.getState()
    const items: MenuItem[] = [
      { path: '/dashboard', name: '工作台', icon: null },
      { path: '/training-jobs', name: '训练任务', icon: null, permission: 'training_jobs:read' },
      { path: '/annotations', name: '数据标注', icon: null, permission: 'annotations:read' },
      { path: '/monitoring', name: '监控', icon: null, permission: 'monitoring:read' },
      { path: '/admin/tenants', name: '租户管理', icon: null, permission: 'tenants:manage' },
      { path: '/inference', name: '推理服务', icon: null, permission: 'inference_services:read' },
    ]
    const filtered = filterMenuItems(items, hasPermission)
    const names = filtered.map((i) => i.name)
    // engineer 经继承链 engineer→annotator 拥有 annotations:read，故可见数据标注；
    // 但无 monitoring 与 admin 权限。
    expect(names).toEqual(['工作台', '训练任务', '数据标注', '推理服务'])
  })

  it('mlops sees annotations and monitoring but not admin tenants', () => {
    useRbacStore.getState().setRole('mlops')
    const { hasPermission } = useRbacStore.getState()
    const items: MenuItem[] = [
      { path: '/annotations', name: '数据标注', icon: null, permission: 'annotations:read' },
      { path: '/monitoring', name: '监控', icon: null, permission: 'monitoring:read' },
      { path: '/admin/tenants', name: '租户管理', icon: null, permission: 'tenants:manage' },
      { path: '/admin/audit-logs', name: '审计日志', icon: null, permission: 'audit_logs:read' },
    ]
    const filtered = filterMenuItems(items, hasPermission)
    const names = filtered.map((i) => i.name)
    expect(names).toEqual(['数据标注', '监控', '审计日志'])
  })

  it('filters parent with no visible children', () => {
    useRbacStore.getState().setRole('annotator')
    const { hasPermission } = useRbacStore.getState()
    const items: MenuItem[] = [
      {
        path: '/admin',
        name: '管理',
        icon: null,
        children: [
          { path: '/admin/tenants', name: '租户管理', icon: null, permission: 'tenants:manage' },
          { path: '/admin/users', name: '用户管理', icon: null, permission: 'users:manage' },
        ],
      },
    ]
    const filtered = filterMenuItems(items, hasPermission)
    expect(filtered).toHaveLength(0)
  })

  it('buildSidebarMenu returns full menu for admin', () => {
    useRbacStore.getState().setRole('admin')
    const { hasPermission } = useRbacStore.getState()
    const menu = buildSidebarMenu(hasPermission)
    expect(menu.length).toBeGreaterThanOrEqual(2)
    const allNames = menu.flatMap((g) => {
      const items = g.children as { name: string; children?: { name: string }[] }[]
      return items.flatMap((c) =>
        c.children ? [c.name, ...c.children.map((cc) => cc.name)] : [c.name],
      )
    })
    expect(allNames).toContain('工作台')
    expect(allNames).toContain('租户管理')
  })

  it('buildSidebarMenu hides admin group for annotator', () => {
    useRbacStore.getState().setRole('annotator')
    const { hasPermission } = useRbacStore.getState()
    const menu = buildSidebarMenu(hasPermission)
    const names = menu.flatMap((g) => (g.children as { name: string }[]).map((c) => c.name))
    expect(names).toContain('工作台')
    expect(names).toContain('数据集')
    expect(names).not.toContain('训练任务')
    expect(names).not.toContain('租户管理')
  })
})
