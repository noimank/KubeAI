import { Navigate, Outlet, useLocation } from 'react-router-dom'
import LoadingPage from '@/components/LoadingPage'
import { useAuthStore } from '@/stores/authStore'

export default function AuthGuard() {
  const { isAuthenticated, isInitializing } = useAuthStore()
  const location = useLocation()

  if (isInitializing) {
    return <LoadingPage tip="正在验证身份..." />
  }

  if (!isAuthenticated) {
    return <Navigate to={`/login?redirect=${encodeURIComponent(location.pathname)}`} replace />
  }

  return <Outlet />
}
