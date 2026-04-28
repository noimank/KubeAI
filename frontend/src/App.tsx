import { useState, useMemo, lazy, Suspense, useEffect } from 'react'
import { App as AntApp, ConfigProvider, Spin, theme as antdTheme } from 'antd'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from './layouts/MainLayout'
import AuthLayout from './layouts/AuthLayout'
import AuthGuard from './components/AuthGuard'
import PermissionGuard from './components/PermissionGuard'
import { setMessageInstance } from './utils/messageHolder'
import { useAuthStore } from './stores/authStore'

const THEME_KEY = 'kubeai_theme'

const LoginPage = lazy(() => import('./pages/login'))
const RegisterPage = lazy(() => import('./pages/register'))
const DashboardPage = lazy(() => import('./pages/dashboard'))
const DatasetsPage = lazy(() => import('./pages/datasets'))
const TrainingJobsPage = lazy(() => import('./pages/training-jobs'))
const ExperimentsPage = lazy(() => import('./pages/experiments'))
const ModelsPage = lazy(() => import('./pages/models'))
const InferencePage = lazy(() => import('./pages/inference'))
const DevEnvironmentsPage = lazy(() => import('./pages/dev-environments'))
const ImagesPage = lazy(() => import('./pages/images'))
const AnnotationsPage = lazy(() => import('./pages/annotations'))
const MonitoringPage = lazy(() => import('./pages/monitoring'))
const ForbiddenPage = lazy(() => import('./pages/403'))
const TenantsPage = lazy(() => import('./pages/admin/tenants'))
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

function getInitialTheme(): 'light' | 'dark' {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return 'light'
}

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

export default function App() {
  const [themeMode] = useState<'light' | 'dark'>(getInitialTheme)
  const initializeAuth = useAuthStore((s) => s.initializeAuth)

  useEffect(() => {
    initializeAuth()
  }, [initializeAuth])

  const themeConfig = useMemo(
    () => ({
      algorithm: themeMode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: '#1677FF',
        borderRadius: 6,
        fontSize: 14,
        colorBgContainer: themeMode === 'dark' ? '#141414' : '#ffffff',
        colorBgLayout: themeMode === 'dark' ? '#000000' : '#f5f5f5',
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
                <Route path="/" element={<AuthGuard />}>
                  <Route element={<MainLayout />}>
                    <Route index element={<Navigate to="/dashboard" replace />} />
                    <Route path="dashboard" element={<DashboardPage />} />
                    <Route
                      path="datasets"
                      element={
                        <PermissionGuard permission="datasets:read">
                          <DatasetsPage />
                        </PermissionGuard>
                      }
                    />
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
