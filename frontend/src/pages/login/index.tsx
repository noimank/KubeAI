import { useState } from 'react'
import { useNavigate, Link, Navigate } from 'react-router-dom'
import { ProForm, ProFormText } from '@ant-design/pro-components'
import { Card, message, Button } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { login } from '@/services/auth'
import { useAuthStore } from '@/stores/authStore'

export default function LoginPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { isAuthenticated, login: authLogin } = useAuthStore()

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await login(values.username, values.password)
      if (res.success && res.data) {
        authLogin(
          { id: '', username: values.username, email: '', role: '', tenant_id: '' },
          res.data.access_token,
          res.data.refresh_token,
        )
        navigate('/dashboard', { replace: true })
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
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/register">
          <Button type="link">没有账号？去注册</Button>
        </Link>
      </div>
    </Card>
  )
}
