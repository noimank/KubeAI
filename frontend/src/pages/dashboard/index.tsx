import { useQuery } from '@tanstack/react-query'
import { getDashboard } from '@/services/dashboard'
import FirstLoginGuide from '@/components/FirstLoginGuide'
import type { DashboardResponse } from '@/types/dashboard'
import HeroBanner from './components/HeroBanner'
import LifecycleFlow from './components/LifecycleFlow'
import RecentActivity from './components/RecentActivity'
import './index.css'

export default function DashboardPage() {
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    refetchInterval: 30_000,
  })

  const dashboardData: DashboardResponse | null = data?.data ?? null

  return (
    <div>
      <HeroBanner />

      <section className="dash-section">
        <div className="dash-section-head">
          <span className="dash-section-title">系统生态 · 全流程闭环</span>
          <span className="dash-section-subtitle">
            数据准备 → 模型开发 → 模型上线 →
            运营反馈，监控评估与业务反馈回流数据，飞轮持续自增强；点击卡片或功能模块可直达对应页面
          </span>
        </div>
        <LifecycleFlow />
      </section>

      <RecentActivity data={dashboardData} />

      <FirstLoginGuide />
    </div>
  )
}
