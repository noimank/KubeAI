import { ProLayout } from '@ant-design/pro-components'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { buildSidebarMenu } from './components/Sidebar'
import { Header } from './components/Header'
import { useIdleTimeout } from '@/hooks/useIdleTimeout'
import { useRbacStore } from '@/stores/rbacStore'
import { useThemeStore } from '@/stores/themeStore'

const NAVIGATE_MAP: Record<string, string> = {
  '/dashboard': '工作台',
  '/datasets': '数据集',
  '/training-jobs': '训练任务',
  '/experiments': '实验追踪',
  '/models': '模型仓库',
  '/inference': '推理服务',
  '/dev-environments': '开发环境',
  '/images': '镜像管理',
  '/annotations': '数据标注',
  '/monitoring': '监控',
  '/admin/tenants': '租户管理',
  '/admin/users': '用户管理',
  '/admin/audit-logs': '审计日志',
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const themeMode = useThemeStore((s) => s.themeMode)

  useIdleTimeout()

  const isDark = themeMode === 'dark'

  return (
    <ProLayout
      title="KubeAI"
      layout="mix"
      navTheme="realDark"
      contentStyle={{ padding: 24 }}
      siderWidth={240}
      fixSiderbar
      fixedHeader
      menuDataRender={() => buildSidebarMenu(hasPermission)}
      menuItemRender={(item, dom) => (
        <div
          onClick={() => {
            if (item.path) navigate(item.path)
          }}
        >
          {dom}
        </div>
      )}
      headerTitleRender={(_logo, title) => <a onClick={() => navigate('/dashboard')}>{title}</a>}
      headerContentRender={() => <Header />}
      location={{ pathname: location.pathname }}
      breadcrumbRender={(routers = []) => [{ path: '/', breadcrumbName: '首页' }, ...routers]}
      token={{
        header: {
          colorBgHeader: isDark ? '#141414' : '#001529',
          colorHeaderTitle: '#fff',
        },
        sider: {
          colorMenuBackground: isDark ? '#1f1f1f' : '#001529',
          colorTextMenu: 'rgba(255,255,255,0.65)',
        },
      }}
    >
      <Outlet />
    </ProLayout>
  )
}

export { NAVIGATE_MAP }
