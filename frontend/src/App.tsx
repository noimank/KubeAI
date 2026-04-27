import { useState, useMemo, lazy, Suspense } from 'react'
import { ConfigProvider, Spin, theme as antdTheme } from 'antd'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from './layouts/MainLayout'
import AuthLayout from './layouts/AuthLayout'

const THEME_KEY = 'kubeai_theme'

const LoginPage = lazy(() => import('./pages/login'))
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

export default function App() {
  const [themeMode] = useState<'light' | 'dark'>(getInitialTheme)

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
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Suspense fallback={<LoadingFallback />}>
            <Routes>
              <Route path="/login" element={<AuthLayout />}>
                <Route index element={<LoginPage />} />
              </Route>
              <Route path="/" element={<MainLayout />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="datasets" element={<DatasetsPage />} />
                <Route path="training-jobs" element={<TrainingJobsPage />} />
                <Route path="experiments" element={<ExperimentsPage />} />
                <Route path="models" element={<ModelsPage />} />
                <Route path="inference" element={<InferencePage />} />
                <Route path="dev-environments" element={<DevEnvironmentsPage />} />
                <Route path="images" element={<ImagesPage />} />
                <Route path="annotations" element={<AnnotationsPage />} />
                <Route path="monitoring" element={<MonitoringPage />} />
                <Route path="admin/tenants" element={<TenantsPage />} />
                <Route path="admin/users" element={<UsersPage />} />
                <Route path="admin/audit-logs" element={<AuditLogsPage />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  )
}
