import {
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  ApiOutlined,
  CodeOutlined,
  AppstoreOutlined,
  EditOutlined,
  MonitorOutlined,
  SettingOutlined,
  TeamOutlined,
  FileSearchOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import type { MenuDataItem } from '@ant-design/pro-components'
import { filterMenuItems, toMenuDataItem } from './sidebar-utils'
import type { MenuItem } from './sidebar-utils'

interface MenuGroup {
  key: string
  name: string
  children: MenuItem[]
}

const MENU_CONFIG: MenuGroup[] = [
  {
    key: 'group-core',
    name: '核心功能',
    children: [
      { path: '/dashboard', name: '工作台', icon: <DashboardOutlined /> },
      {
        path: '/datasets',
        name: '数据集',
        icon: <DatabaseOutlined />,
        permission: 'datasets:read',
      },
      {
        path: '/training-jobs',
        name: '训练任务',
        icon: <ExperimentOutlined />,
        permission: 'training_jobs:read',
      },
      {
        path: '/experiments',
        name: '实验追踪',
        icon: <FileSearchOutlined />,
        permission: 'experiments:read',
      },
      {
        path: '/models',
        name: '模型仓库',
        icon: <SafetyCertificateOutlined />,
        permission: 'models:read',
      },
      {
        path: '/inference',
        name: '推理服务',
        icon: <ApiOutlined />,
        permission: 'inference_services:read',
      },
    ],
  },
  {
    key: 'group-dev',
    name: '开发',
    children: [
      {
        path: '/dev-environments',
        name: '开发环境',
        icon: <CodeOutlined />,
        permission: 'dev_environments:read',
      },
      { path: '/images', name: '镜像管理', icon: <AppstoreOutlined />, permission: 'images:read' },
      {
        path: '/annotations',
        name: '数据标注',
        icon: <EditOutlined />,
        permission: 'annotations:read',
      },
    ],
  },
  {
    key: 'group-system',
    name: '系统',
    children: [
      {
        path: '/monitoring',
        name: '监控',
        icon: <MonitorOutlined />,
        permission: 'monitoring:read',
      },
      {
        path: '/admin',
        name: '管理',
        icon: <SettingOutlined />,
        children: [
          {
            path: '/admin/tenants',
            name: '租户管理',
            icon: <TeamOutlined />,
            permission: 'tenants:manage',
          },
          {
            path: '/admin/users',
            name: '用户管理',
            icon: <TeamOutlined />,
            permission: 'users:manage',
          },
          {
            path: '/admin/audit-logs',
            name: '审计日志',
            icon: <FileSearchOutlined />,
            permission: 'audit_logs:read',
          },
        ],
      },
    ],
  },
]

export function buildSidebarMenu(hasPermission: (permission: string) => boolean): MenuDataItem[] {
  const result: MenuDataItem[] = []
  for (const group of MENU_CONFIG) {
    const filtered = filterMenuItems(group.children, hasPermission)
    if (filtered.length === 0) continue
    result.push({
      key: group.key,
      name: group.name,
      children: filtered.map(toMenuDataItem),
    })
  }
  return result
}
