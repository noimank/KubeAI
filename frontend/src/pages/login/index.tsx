import { useEffect, useState } from 'react'
import { useNavigate, Link, Navigate, useSearchParams } from 'react-router-dom'
import { ProForm, ProFormText } from '@ant-design/pro-components'
import { Button, Card } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { login, getAuthConfig, getCurrentUser } from '@/services/auth'
import { getOAuthProviders } from '@/services/oauth'
import { useAuthStore } from '@/stores/authStore'
import { getMessageInstance } from '@/utils/messageHolder'
import { APP_TITLE } from '@/utils/constants'
import OAuthButtons from './components/OAuthButtons'
import './index.css'

const platformStats = ['GPU 资源调度', '多租户权限隔离', '训练到推理闭环']

const trustItems = ['安全访问', '审计可追溯']

function ProductIcon({ className = '' }: { className?: string }) {
  return <img className={`login-product-icon ${className}`} src="/favicon.svg" alt="" />
}

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [allowUserRegistration, setAllowUserRegistration] = useState(false)
  const [redirecting, setRedirecting] = useState<{ name: string; displayName: string } | null>(null)
  const [redirectTimedOut, setRedirectTimedOut] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { isAuthenticated, login: authLogin } = useAuthStore()
  const setTokens = useAuthStore((s) => s.setTokens)

  useEffect(() => {
    let mounted = true
    let timeoutId: ReturnType<typeof setTimeout>
    Promise.all([getAuthConfig(), getOAuthProviders()])
      .then(([configRes, providersRes]) => {
        if (!mounted) return
        setAllowUserRegistration(Boolean(configRes.data?.allowUserRegistration))
        const oidcAutoRedirect = Boolean(configRes.data?.oidcAutoRedirect)
        const providerList = providersRes.success && providersRes.data ? providersRes.data : []
        if (oidcAutoRedirect && providerList.length > 0) {
          const provider = providerList[0]
          setRedirecting({ name: provider.name, displayName: provider.displayName })
          window.location.href = `/api/auth/oauth/${provider.name}/authorize`
          // If redirect hasn't happened after 8s, show fallback
          timeoutId = setTimeout(() => {
            if (mounted) setRedirectTimedOut(true)
          }, 8000)
        }
      })
      .catch(() => {
        if (mounted) {
          setAllowUserRegistration(false)
        }
      })
    return () => {
      mounted = false
      clearTimeout(timeoutId)
    }
  }, [])

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  if (redirecting) {
    return (
      <div className="login-page">
        <div className="login-background" aria-hidden="true">
          <div className="login-scanline" />
          <div className="login-circuit login-circuit-left" />
          <div className="login-circuit login-circuit-right" />
        </div>

        <main className="login-shell">
          <section className="login-brand-panel">
            <div className="login-product-mark">
              <ProductIcon className="login-logo-mark" />
              <span>{APP_TITLE}</span>
            </div>
          </section>

          <section className="login-form-panel">
            <Card className="login-card login-redirect-card elevated-card" variant="borderless">
              <div className="login-redirect-header">
                <div className="login-redirect-provider-icon">
                  <ProductIcon className="login-redirect-icon-img" />
                </div>
                <h2>{redirecting.displayName}</h2>
                <p className="login-redirect-desc">正在跳转至企业身份认证，请稍候…</p>
              </div>

              <div className="login-redirect-progress">
                <div className="login-redirect-bar-track">
                  <div className="login-redirect-bar-fill" />
                </div>
              </div>

              {redirectTimedOut && (
                <div className="login-redirect-fallback">
                  <p>跳转未响应？请确认已开启浏览器弹窗拦截白名单，或返回账号密码登录。</p>
                  <Button
                    type="primary"
                    block
                    size="large"
                    className="login-submit-button"
                    onClick={() => setRedirecting(null)}
                  >
                    返回账号密码登录
                  </Button>
                </div>
              )}
            </Card>
          </section>
        </main>
      </div>
    )
  }

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await login(values.username, values.password)
      if (res.success && res.data) {
        setTokens(res.data.accessToken, res.data.refreshToken)
        const userRes = await getCurrentUser()
        if (userRes.success && userRes.data) {
          authLogin(userRes.data, res.data.accessToken, res.data.refreshToken)
        } else {
          getMessageInstance()?.error('获取用户信息失败')
          return
        }
        const redirect = searchParams.get('redirect') || '/dashboard'
        navigate(redirect, { replace: true })
      }
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { message?: string } } }
      const msg = error.response?.data?.message
      if (msg?.includes('锁定')) {
        getMessageInstance()?.error({ content: msg, duration: 5 })
      } else {
        getMessageInstance()?.error({ content: msg || '用户名或密码错误', duration: 5 })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-background" aria-hidden="true">
        <div className="login-scanline" />
        <div className="login-circuit login-circuit-left" />
        <div className="login-circuit login-circuit-right" />
      </div>

      <main className="login-shell">
        <section className="login-brand-panel">
          <div className="login-product-mark">
            <ProductIcon className="login-logo-mark" />
            <span>{APP_TITLE}</span>
          </div>

          <div className="login-hero-copy">
            <div className="login-eyebrow">
              <ProductIcon className="login-eyebrow-icon" />
              云原生 AI 平台
            </div>
            <h1>面向企业 AI 工程的统一控制台</h1>
            <p>统一管理数据、训练、模型与推理服务，让 AI 工作负载稳定运行在 Kubernetes 上。</p>
          </div>

          <div className="login-stats" aria-label="平台能力">
            {platformStats.map((item) => (
              <div className="login-stat" key={item}>
                <ProductIcon className="login-stat-icon" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="login-form-panel">
          <Card className="login-card elevated-card" variant="borderless">
            <div className="login-card-header">
              <ProductIcon className="login-card-icon" />
              <div>
                <h2>登录控制台</h2>
                <p>进入 {APP_TITLE} 工作空间</p>
              </div>
            </div>

            <div className="login-trust-row">
              {trustItems.map((item) => (
                <span key={item}>
                  <ProductIcon className="login-trust-icon" />
                  {item}
                </span>
              ))}
            </div>

            <ProForm<{ username: string; password: string }>
              className="login-form"
              onFinish={handleSubmit}
              submitter={{
                render: () => (
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    disabled={loading}
                    block
                    size="large"
                    icon={<ProductIcon className="login-button-icon" />}
                    className="login-submit-button"
                  >
                    进入平台
                  </Button>
                ),
              }}
            >
              <ProFormText
                name="username"
                label="用户名 / 邮箱"
                placeholder="请输入用户名或邮箱"
                rules={[{ required: true, message: '请输入用户名或邮箱' }]}
                fieldProps={{ prefix: <UserOutlined />, size: 'large' }}
              />
              <ProFormText.Password
                name="password"
                label="密码"
                placeholder="请输入密码"
                rules={[{ required: true, message: '请输入密码' }]}
                fieldProps={{ prefix: <LockOutlined />, size: 'large' }}
              />
            </ProForm>

            <OAuthButtons />

            {allowUserRegistration ? (
              <div className="login-register-link">
                还没有工作空间账号？
                <Link to="/register">立即注册</Link>
              </div>
            ) : (
              <div className="login-register-disabled">
                自助注册暂未开放，请联系平台管理员开通账号
              </div>
            )}
          </Card>
        </section>
      </main>
    </div>
  )
}
