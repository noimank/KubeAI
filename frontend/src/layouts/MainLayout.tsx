import { ConfigProvider, theme as antdTheme } from 'antd'
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
  '/datasets/:id': '数据集详情',
  '/training-jobs': '训练任务',
  '/experiments': '实验追踪',
  '/models': '模型仓库',
  '/inference': '推理服务',
  '/dev-environments': '开发环境',
  '/algorithms': '算法管理',
  '/algorithms/:id': '算法详情',
  '/images': '镜像管理',
  '/annotations': '数据标注',
  '/monitoring': '监控',
  '/notifications': '通知中心',
  '/admin/tenants': '租户管理',
  '/admin/users': '用户管理',
  '/admin/audit-logs': '审计日志',
  '/profile': '个人设置',
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const themeMode = useThemeStore((s) => s.themeMode)

  useIdleTimeout()

  const isDark = themeMode === 'dark'

  // realDark gives correct dark styling for sidebar/header, but applies dark
  // algorithm to the content area too. Wrap <Outlet> in a ConfigProvider that
  // restores the correct algorithm so page content renders properly.
  const contentAlgorithm = isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm

  return (
    <ProLayout
      title="KubeAI"
      logo="/favicon.svg"
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
      headerTitleRender={(logo, title) => (
        <a
          onClick={() => navigate('/dashboard')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
        >
          {logo}
          {title}
        </a>
      )}
      headerContentRender={false}
      actionsRender={() => <Header />}
      location={{ pathname: location.pathname }}
      breadcrumbRender={(routers = []) => [{ path: '/', breadcrumbName: '首页' }, ...routers]}
      token={{
        header: {
          colorBgHeader: isDark ? '#1f1f1f' : '#001529',
        },
        sider: {
          colorMenuBackground: isDark ? '#1f1f1f' : '#001529',
        },
      }}
    >
      <ConfigProvider theme={{ algorithm: contentAlgorithm }}>
        <Outlet />
      </ConfigProvider>
    </ProLayout>
  )
}

export { NAVIGATE_MAP }
