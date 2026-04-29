import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Spin, App } from 'antd'
import { oauthCallback } from '@/services/oauth'
import { getCurrentUser } from '@/services/auth'
import { useAuthStore } from '@/stores/authStore'

export default function OAuthCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { message } = App.useApp()
  const authLogin = useAuthStore((s) => s.login)
  const setTokens = useAuthStore((s) => s.setTokens)
  const called = useRef(false)

  useEffect(() => {
    if (called.current) return
    called.current = true

    const code = searchParams.get('code')
    const state = searchParams.get('state')

    if (!code || !state) {
      message.error('无效的 OAuth 回调参数')
      navigate('/login', { replace: true })
      return
    }

    oauthCallback('oidc', code, state)
      .then(async (res) => {
        if (res.success && res.data) {
          setTokens(res.data.accessToken, res.data.refreshToken)
          const userRes = await getCurrentUser()
          if (userRes.success && userRes.data) {
            authLogin(userRes.data, res.data.accessToken, res.data.refreshToken)
            navigate('/dashboard', { replace: true })
          } else {
            message.error('获取用户信息失败')
            navigate('/login', { replace: true })
          }
        }
      })
      .catch((err: unknown) => {
        const error = err as { response?: { data?: { message?: string } } }
        message.error(error.response?.data?.message || 'OAuth 登录失败')
        navigate('/login', { replace: true })
      })
  }, [searchParams, navigate, message, authLogin, setTokens])

  return (
    <div
      style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}
    >
      <Spin size="large" tip="正在处理登录..." />
    </div>
  )
}
