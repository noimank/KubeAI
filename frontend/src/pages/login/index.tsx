import { useState } from 'react'
import { useNavigate, Link, Navigate, useSearchParams } from 'react-router-dom'
import { ProForm, ProFormText } from '@ant-design/pro-components'
import { App, Card, Button, Divider } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { login, getCurrentUser } from '@/services/auth'
import { useAuthStore } from '@/stores/authStore'
import OAuthButtons from './components/OAuthButtons'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { message } = App.useApp()
  const { isAuthenticated, login: authLogin } = useAuthStore()
  const setTokens = useAuthStore((s) => s.setTokens)

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
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
          message.error('获取用户信息失败')
          return
        }
        const redirect = searchParams.get('redirect') || '/dashboard'
        navigate(redirect, { replace: true })
      }
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { message?: string } } }
      const msg = error.response?.data?.message
      if (msg?.includes('锁定')) {
        message.error({ content: msg, duration: 5 })
      } else {
        message.error({ content: msg || '用户名或密码错误', duration: 5 })
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card style={{ width: '100%', maxWidth: 600 }}>
      <ProForm<{ username: string; password: string }>
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
            >
              登录
            </Button>
          ),
        }}
      >
        <h2 style={{ textAlign: 'center', marginBottom: 24 }}>登录</h2>
        <ProFormText
          name="username"
          label="用户名"
          placeholder="请输入用户名"
          rules={[{ required: true, message: '请输入用户名' }]}
          fieldProps={{ prefix: <UserOutlined /> }}
        />
        <ProFormText.Password
          name="password"
          label="密码"
          placeholder="请输入密码"
          rules={[{ required: true, message: '请输入密码' }]}
          fieldProps={{ prefix: <LockOutlined /> }}
        />
      </ProForm>
      <Divider>其他登录方式</Divider>
      <OAuthButtons />
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/register">
          <Button type="link">没有账号？去注册</Button>
        </Link>
      </div>
    </Card>
  )
}
