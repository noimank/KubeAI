import { useMemo, lazy, Suspense, useEffect } from 'react'
import { App as AntApp, ConfigProvider, Spin, theme as antdTheme } from 'antd'
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from './layouts/MainLayout'
import AuthLayout from './layouts/AuthLayout'
import AuthGuard from './components/AuthGuard'
import PermissionGuard from './components/PermissionGuard'
import { setMessageInstance } from './utils/messageHolder'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'

const LoginPage = lazy(() => import('./pages/login'))
const OAuthCallbackPage = lazy(() => import('./pages/login/callback'))
const RegisterPage = lazy(() => import('./pages/register'))
const DashboardPage = lazy(() => import('./pages/dashboard'))
const DatasetsPage = lazy(() => import('./pages/datasets'))
const DatasetDetailPage = lazy(() => import('./pages/datasets/detail'))
const TrainingJobsPage = lazy(() => import('./pages/training-jobs'))
const ExperimentsPage = lazy(() => import('./pages/experiments'))
const ModelsPage = lazy(() => import('./pages/models'))
const InferencePage = lazy(() => import('./pages/inference'))
const DevEnvironmentsPage = lazy(() => import('./pages/dev-environments'))
const ImagesPage = lazy(() => import('./pages/images'))
const AnnotationsPage = lazy(() => import('./pages/annotations'))
const MonitoringPage = lazy(() => import('./pages/monitoring'))
const ForbiddenPage = lazy(() => import('./pages/403'))
const InvitePage = lazy(() => import('./pages/invite'))
const TenantsPage = lazy(() => import('./pages/admin/tenants'))
const TenantDetailPage = lazy(() => import('./pages/admin/tenants/detail'))
const UsersPage = lazy(() => import('./pages/admin/users'))
const AuditLogsPage = lazy(() => import('./pages/admin/audit-logs'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function LoadingFallback() {
  return (
    <div
      style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}
    >
      <Spin spinning />
    </div>
  )
}

function MessageHolder() {
  const { message } = AntApp.useApp()
  useMemo(() => {
    setMessageInstance(message)
  }, [message])
  return null
}

const FONT_FAMILY =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', 'Noto Sans', 'Noto Sans SC', sans-serif"
const FONT_FAMILY_CODE =
  "'SF Mono', 'Fira Code', 'Fira Mono', 'Roboto Mono', 'SFMono-Regular', Menlo, Monaco, Consolas, monospace"

export default function App() {
  const themeMode = useThemeStore((s) => s.themeMode)
  const initializeAuth = useAuthStore((s) => s.initializeAuth)

  useEffect(() => {
    initializeAuth()
  }, [initializeAuth])

  const themeConfig = useMemo(
    () => ({
      algorithm: themeMode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: '#1677FF',
        colorSuccess: '#52C41A',
        colorWarning: '#FAAD14',
        colorError: '#FF4D4F',
        colorLink: '#1677FF',
        fontFamily: FONT_FAMILY,
        fontFamilyCode: FONT_FAMILY_CODE,
        borderRadius: 6,
        fontSize: 14,
        lineHeight: 1.5714,
        sizeStep: 4,
        sizeUnit: 4,
        wireframe: false,
        colorBgContainer: themeMode === 'dark' ? '#141414' : '#ffffff',
        colorBgLayout: themeMode === 'dark' ? '#000000' : '#f5f5f5',
        colorTextSecondary:
          themeMode === 'dark' ? 'rgba(255, 255, 255, 0.65)' : 'rgba(0, 0, 0, 0.65)',
        colorTextTertiary:
          themeMode === 'dark' ? 'rgba(255, 255, 255, 0.45)' : 'rgba(0, 0, 0, 0.45)',
        colorTextQuaternary:
          themeMode === 'dark' ? 'rgba(255, 255, 255, 0.25)' : 'rgba(0, 0, 0, 0.25)',
        colorFillAlter: themeMode === 'dark' ? '#1f1f1f' : '#fafafa',
        colorFillSecondary: themeMode === 'dark' ? '#262626' : '#f5f5f5',
      },
      components: {
        Button: {
          primaryShadow: '0 2px 0 rgba(5, 145, 255, 0.1)',
          defaultBorderColor: themeMode === 'dark' ? '#424242' : '#d9d9d9',
        },
        Input: {
          borderRadius: 6,
          controlHeight: 32,
          paddingInline: 12,
        },
        Select: {
          borderRadius: 6,
          controlHeight: 32,
          paddingInline: 12,
        },
        Table: {
          borderRadius: 6,
          cellFontSize: 14,
          headerBg: themeMode === 'dark' ? '#1f1f1f' : '#fafafa',
          headerColor: themeMode === 'dark' ? 'rgba(255, 255, 255, 0.85)' : 'rgba(0, 0, 0, 0.88)',
          headerSortActiveBg: themeMode === 'dark' ? '#262626' : '#f0f0f0',
          headerSortHoverBg: themeMode === 'dark' ? '#303030' : '#f2f2f2',
          rowHoverBg: themeMode === 'dark' ? '#1f1f1f' : '#fafafa',
          borderColor: themeMode === 'dark' ? '#303030' : '#f0f0f0',
        },
        Card: {
          borderRadiusLG: 8,
        },
        Descriptions: {
          borderRadiusLG: 8,
          labelBg: themeMode === 'dark' ? '#000000' : '#f5f5f5',
        },
      },
      cssVar: true,
    }),
    [themeMode],
  )

  return (
    <ConfigProvider locale={zhCN} theme={themeConfig}>
      <AntApp>
        <MessageHolder />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <Suspense fallback={<LoadingFallback />}>
              <Routes>
                <Route path="/login" element={<AuthLayout />}>
                  <Route index element={<LoginPage />} />
                </Route>
                <Route path="/register" element={<AuthLayout />}>
                  <Route index element={<RegisterPage />} />
                </Route>
                <Route path="/auth/callback" element={<AuthLayout />}>
                  <Route index element={<OAuthCallbackPage />} />
                </Route>
                <Route path="/invite" element={<InvitePage />} />
                <Route path="/" element={<AuthGuard />}>
                  <Route element={<MainLayout />}>
                    <Route index element={<Navigate to="/dashboard" replace />} />
                    <Route path="dashboard" element={<DashboardPage />} />
                    <Route
                      path="datasets"
                      element={
                        <PermissionGuard permission="datasets:read">
                          <Outlet />
                        </PermissionGuard>
                      }
                    >
                      <Route index element={<DatasetsPage />} />
                      <Route path=":id" element={<DatasetDetailPage />} />
                    </Route>
                    <Route
                      path="training-jobs"
                      element={
                        <PermissionGuard permission="training_jobs:read">
                          <TrainingJobsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="experiments"
                      element={
                        <PermissionGuard permission="experiments:read">
                          <ExperimentsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="models"
                      element={
                        <PermissionGuard permission="models:read">
                          <ModelsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="inference"
                      element={
                        <PermissionGuard permission="inference_services:read">
                          <InferencePage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="dev-environments"
                      element={
                        <PermissionGuard permission="dev_environments:read">
                          <DevEnvironmentsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="images"
                      element={
                        <PermissionGuard permission="images:read">
                          <ImagesPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="annotations"
                      element={
                        <PermissionGuard permission="annotations:read">
                          <AnnotationsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="monitoring"
                      element={
                        <PermissionGuard permission="monitoring:read">
                          <MonitoringPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="admin/tenants"
                      element={
                        <PermissionGuard permission="tenants:manage">
                          <TenantsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="admin/tenants/:id"
                      element={
                        <PermissionGuard permission="tenants:manage">
                          <TenantDetailPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="admin/users"
                      element={
                        <PermissionGuard permission="users:manage">
                          <UsersPage />
                        </PermissionGuard>
                      }
                    />
                    <Route
                      path="admin/audit-logs"
                      element={
                        <PermissionGuard permission="audit_logs:read">
                          <AuditLogsPage />
                        </PermissionGuard>
                      }
                    />
                    <Route path="403" element={<ForbiddenPage />} />
                  </Route>
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  )
}
