import { useAuthStore } from '@/stores/authStore'

export default function HeroBanner() {
  const appName = useAuthStore((s) => s.appName)

  return (
    <div className="dash-hero">
      <div className="dash-hero-title">{appName} · 一站式企业级 AI 平台</div>
      <p className="dash-hero-desc">
        覆盖<strong>数据准备 → 模型开发 → 模型上线 → 运营反馈</strong>
        的全流程闭环：业务反馈持续回流优化数据，数据驱动训练迭代，训练产出更优的在线推理服务，让 AI
        能力快速落地。
      </p>
    </div>
  )
}
