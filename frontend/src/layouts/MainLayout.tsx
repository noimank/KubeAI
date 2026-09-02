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
      // CloudAxis 配色规格 (同步样式方案.md): 白色头部 + 暗蓝 #001529 侧边菜单。
      // 注意不要设 navTheme="realDark" —— ProConfigProvider 会把暗色算法注入整个布局(含头部与弹层),
      // 仅靠 sider token 即可在亮色主题下驱动暗色菜单(v5 经独立 ConfigProvider 只作用于侧栏)。
      token={{
        header: {
          colorBgHeader: '#ffffff',
        },
        sider: {
          colorMenuBackground: '#001529',
          colorTextMenu: 'rgba(255, 255, 255, 0.85)',
          colorTextMenuItemHover: '#ffffff',
          colorTextMenuSelected: '#ffffff',
          colorBgMenuItemHover: 'rgba(255, 255, 255, 0.12)',
          colorBgMenuItemSelected: '#1890ff',
          colorMenuItemDivider: 'rgba(255, 255, 255, 0.1)',
        },
        bgLayout: '#f5f7fa',
      }}
    >
      <Outlet />
    </ProLayout>
  )
}

export { NAVIGATE_MAP }
