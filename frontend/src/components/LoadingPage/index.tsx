import { Spin } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import './index.css'

interface LoadingPageProps {
  tip?: string
}

export default function LoadingPage({ tip }: LoadingPageProps) {
  const appName = useAuthStore((s) => s.appName)

  return (
    <div className="loading-page">
      <div className="loading-page-content">
        <img className="loading-page-icon" src="/logo.jpg" alt="" />
        <h1 className="loading-page-brand">{appName}</h1>
        <div className="loading-page-spinner">
          <Spin size="large" />
        </div>
        {tip && <p className="loading-page-text">{tip}</p>}
      </div>
    </div>
  )
}
