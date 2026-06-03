import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, Form, Input, Result, Space, Spin } from 'antd'
import { getInvitationInfo, acceptInvitation } from '@/services/auth'
import { getMessageInstance } from '@/utils/messageHolder'
import { useAuthStore } from '@/stores/authStore'
import type { InvitationInfo } from '@/types/tenant'
import { ROLE_LABELS } from '@/utils/roleLabels'

export default function InvitePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [info, setInfo] = useState<InvitationInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [needConfirm, setNeedConfirm] = useState(false)

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)
  const setTokens = useAuthStore((s) => s.setTokens)
  const initializeAuth = useAuthStore((s) => s.initializeAuth)

  useEffect(() => {
    if (!token) {
      setError('缺少邀请令牌')
      setLoading(false)
      return
    }
    getInvitationInfo(token)
      .then((res) => {
        if (res.success && res.data) {
          setInfo(res.data)
        } else {
          setError('邀请无效或已过期')
        }
      })
      .catch(() => {
        setError('邀请无效或已过期')
      })
      .finally(() => setLoading(false))
  }, [token])

  const handleRegister = async (values: {
    username: string
    password: string
    confirmPassword: string
  }) => {
    setSubmitting(true)
    try {
      const res = await acceptInvitation({
        token,
        username: values.username,
        password: values.password,
        confirmPassword: values.confirmPassword,
      })
      if (res.success && res.data) {
        setTokens(res.data.accessToken, res.data.refreshToken)
        await initializeAuth()
        getMessageInstance()?.success('注册成功，已加入租户')
        navigate('/dashboard', { replace: true })
      }
    } catch {
      // interceptor handles error toast
    } finally {
      setSubmitting(false)
    }
  }

  const handleAcceptAsLoggedIn = async () => {
    setSubmitting(true)
    try {
      const res = await acceptInvitation({ token, force: needConfirm })
      if (res.success && res.data) {
        setTokens(res.data.accessToken, res.data.refreshToken)
        await initializeAuth()
        getMessageInstance()?.success('已加入租户')
        navigate('/dashboard', { replace: true })
      }
    } catch {
      // interceptor handles error toast
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}
      >
        <Spin size="large" tip="加载邀请信息...">
          <div />
        </Spin>
      </div>
    )
  }

  if (error || !info) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}
      >
        <Result
          status="error"
          title="邀请无效"
          subTitle={error || '邀请链接无效或已过期'}
          extra={<Button onClick={() => navigate('/login')}>返回登录</Button>}
        />
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: 'var(--bg-page)',
      }}
    >
      <Card style={{ width: 420, borderRadius: 8 }} className="elevated-card" title="邀请加入租户">
        <p style={{ fontSize: 16, marginBottom: 24 }}>
          您被邀请加入租户「<strong>{info.tenantDisplayName}</strong>」作为
          <strong>{ROLE_LABELS[info.role] || info.role}</strong>
        </p>

        {isAuthenticated && user ? (
          <div>
            {user.tenantId && !needConfirm ? (
              <div>
                <p style={{ color: 'var(--text-warning)', marginBottom: 16 }}>
                  您当前已属于一个租户，接受邀请将转移到新租户。确认继续？
                </p>
                <Space>
                  <Button type="primary" onClick={() => setNeedConfirm(true)} loading={submitting}>
                    确认转移
                  </Button>
                  <Button onClick={() => navigate('/dashboard')}>取消</Button>
                </Space>
              </div>
            ) : (
              <Button type="primary" block onClick={handleAcceptAsLoggedIn} loading={submitting}>
                确认加入
              </Button>
            )}
          </div>
        ) : (
          <Form layout="vertical" onFinish={handleRegister}>
            <Form.Item label="邮箱">
              <Input value={info.email} disabled />
            </Form.Item>
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input placeholder="请输入用户名" />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, min: 8, message: '密码至少 8 个字符' }]}
            >
              <Input.Password placeholder="请输入密码" />
            </Form.Item>
            <Form.Item
              name="confirmPassword"
              label="确认密码"
              dependencies={['password']}
              rules={[
                { required: true, message: '请确认密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) return Promise.resolve()
                    return Promise.reject(new Error('两次输入的密码不一致'))
                  },
                }),
              ]}
            >
              <Input.Password placeholder="请再次输入密码" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button type="primary" htmlType="submit" block loading={submitting}>
                注册并加入
              </Button>
            </Form.Item>
            <div style={{ marginTop: 12, textAlign: 'center' }}>
              已有账号？
              <Button type="link" size="small" onClick={() => navigate('/login')}>
                先登录
              </Button>
            </div>
          </Form>
        )}
      </Card>
    </div>
  )
}
