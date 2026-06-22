import { Spin } from 'antd'
import { APP_TITLE } from '@/utils/constants'
import './index.css'

interface LoadingPageProps {
  tip?: string
}

export default function LoadingPage({ tip }: LoadingPageProps) {
  return (
    <div className="loading-page">
      <div className="loading-page-content">
        <img className="loading-page-icon" src="/favicon.svg" alt="" />
        <h1 className="loading-page-brand">{APP_TITLE}</h1>
        <div className="loading-page-spinner">
          <Spin size="large" />
        </div>
        {tip && <p className="loading-page-text">{tip}</p>}
      </div>
    </div>
  )
}
