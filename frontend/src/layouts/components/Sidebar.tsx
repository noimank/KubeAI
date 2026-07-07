import {
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  ApiOutlined,
  CodeOutlined,
  AppstoreOutlined,
  EditOutlined,
  MonitorOutlined,
  TeamOutlined,
  FileSearchOutlined,
  SafetyCertificateOutlined,
  BellOutlined,
  FolderOpenOutlined,
  UserOutlined,
  CalculatorOutlined,
  ThunderboltOutlined,
  BuildOutlined,
} from '@ant-design/icons'
import type { MenuDataItem } from '@ant-design/pro-components'
import { filterMenuItems, toMenuDataItem } from './sidebar-utils'
import type { MenuItem } from './sidebar-utils'

interface MenuGroup {
  type: 'group'
  key: string
  name: string
  children: MenuItem[]
}

interface MenuStandalone {
  type: 'item'
  path: string
  name: string
  icon: React.ReactNode
  permission?: string
}

type MenuEntry = MenuGroup | MenuStandalone

const MENU_CONFIG: MenuEntry[] = [
  {
    type: 'item',
    path: '/dashboard',
    name: '系统概览',
    icon: <DashboardOutlined />,
  },
  {
    type: 'group',
    key: 'group-data',
    name: '数据管理',
    children: [
      {
        path: '/datasets',
        name: '数据集',
        icon: <DatabaseOutlined />,
        permission: 'datasets:read',
      },
      {
        path: '/annotations',
        name: '数据标注',
        icon: <EditOutlined />,
        permission: 'annotations:read',
      },
    ],
  },
  {
    type: 'group',
    key: 'group-dev-train',
    name: '开发与训练',
    children: [
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
        path: '/algorithms',
        name: '算法管理',
        icon: <FolderOpenOutlined />,
        permission: 'algorithms:read',
      },
      {
        path: '/dev-environments',
        name: '开发环境',
        icon: <CodeOutlined />,
        permission: 'dev_environments:read',
      },
      { path: '/images', name: '镜像管理', icon: <AppstoreOutlined />, permission: 'images:read' },
    ],
  },
  {
    type: 'group',
    key: 'group-business-algorithm',
    name: '业务算法库',
    children: [
      {
        path: '/business-algorithm/metaheuristic',
        name: '元启发算法',
        icon: <ThunderboltOutlined />,
      },
      {
        path: '/business-algorithm/data-planning',
        name: '数据规划',
        icon: <CalculatorOutlined />,
      },
      {
        path: '/business-algorithm/heuristic-rules',
        name: '启发式规则',
        icon: <BuildOutlined />,
      },
    ],
  },
  {
    type: 'group',
    key: 'group-inference',
    name: '推理服务',
    children: [
      {
        path: '/inference',
        name: '推理服务',
        icon: <ApiOutlined />,
        permission: 'inference_services:read',
      },
      {
        path: '/models',
        name: '模型仓库',
        icon: <SafetyCertificateOutlined />,
        permission: 'models:read',
      },
    ],
  },
  {
    type: 'group',
    key: 'group-admin',
    name: '管理',
    children: [
      {
        path: '/monitoring',
        name: '监控',
        icon: <MonitorOutlined />,
        permission: 'monitoring:read',
      },
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
  {
    type: 'group',
    key: 'group-system',
    name: '系统',
    children: [
      {
        path: '/notifications',
        name: '通知中心',
        icon: <BellOutlined />,
        permission: 'notifications:read',
      },
      {
        path: '/profile',
        name: '个人设置',
        icon: <UserOutlined />,
      },
    ],
  },
]

export function buildSidebarMenu(hasPermission: (permission: string) => boolean): MenuDataItem[] {
  const result: MenuDataItem[] = []
  for (const entry of MENU_CONFIG) {
    if (entry.type === 'group') {
      const filtered = filterMenuItems(entry.children, hasPermission)
      if (filtered.length === 0) continue
      result.push({
        key: entry.key,
        name: entry.name,
        children: filtered.map(toMenuDataItem),
      })
    } else {
      if (entry.permission && !hasPermission(entry.permission)) continue
      result.push({
        key: entry.path,
        ...toMenuDataItem({
          path: entry.path,
          name: entry.name,
          icon: entry.icon,
          permission: entry.permission,
        }),
      })
    }
  }
  return result
}
