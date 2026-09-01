import { ProLayout } from '@ant-design/pro-components'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { buildSidebarMenu } from './components/Sidebar'
import { Header } from './components/Header'
import { useIdleTimeout } from '@/hooks/useIdleTimeout'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'

const NAVIGATE_MAP: Record<string, string> = {
  '/dashboard': '系统概览',
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
  '/data-explore': '数据探索',
  '/monitoring': '监控',
  '/notifications': '通知中心',
  '/business-algorithm': '业务算法库',
  '/admin/tenants': '租户管理',
  '/admin/users': '用户管理',
  '/admin/audit-logs': '审计日志',
  '/profile': '个人设置',
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const enableBusinessAlgorithm = useAuthStore((s) => s.enableBusinessAlgorithm)
  const appName = useAuthStore((s) => s.appName)

  useIdleTimeout()

  return (
    <ProLayout
      title={appName}
      logo={<img src="/logo.jpg" alt="" style={{ height: 32, width: 'auto', borderRadius: 7 }} />}
      layout="mix"
      navTheme="realDark"
      contentStyle={{ padding: 24 }}
      siderWidth={240}
      fixSiderbar
      fixedHeader
      menuDataRender={() => buildSidebarMenu(hasPermission, enableBusinessAlgorithm)}
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
          colorBgHeader: '#001529',
        },
        sider: {
          colorMenuBackground: '#001529',
        },
      }}
    >
      <Outlet />
    </ProLayout>
  )
}

export { NAVIGATE_MAP }
