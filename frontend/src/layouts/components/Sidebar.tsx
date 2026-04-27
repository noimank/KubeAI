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

export function Sidebar(): MenuDataItem[] {
  return [
    {
      key: 'group-core',
      name: '核心功能',
      children: [
        { path: '/dashboard', name: '工作台', icon: <DashboardOutlined /> },
        { path: '/datasets', name: '数据集', icon: <DatabaseOutlined /> },
        { path: '/training-jobs', name: '训练任务', icon: <ExperimentOutlined /> },
        { path: '/experiments', name: '实验追踪', icon: <FileSearchOutlined /> },
        { path: '/models', name: '模型仓库', icon: <SafetyCertificateOutlined /> },
        { path: '/inference', name: '推理服务', icon: <ApiOutlined /> },
      ],
    },
    {
      key: 'group-dev',
      name: '开发',
      children: [
        { path: '/dev-environments', name: '开发环境', icon: <CodeOutlined /> },
        { path: '/images', name: '镜像管理', icon: <AppstoreOutlined /> },
        { path: '/annotations', name: '数据标注', icon: <EditOutlined /> },
      ],
    },
    {
      key: 'group-system',
      name: '系统',
      children: [
        { path: '/monitoring', name: '监控', icon: <MonitorOutlined /> },
        {
          path: '/admin',
          name: '管理',
          icon: <SettingOutlined />,
          children: [
            { path: '/admin/tenants', name: '租户管理', icon: <TeamOutlined /> },
            { path: '/admin/users', name: '用户管理', icon: <TeamOutlined /> },
            { path: '/admin/audit-logs', name: '审计日志', icon: <FileSearchOutlined /> },
          ],
        },
      ],
    },
  ]
}
