import { useEffect, useState } from 'react'
import { useNavigate, Link, Navigate, useSearchParams } from 'react-router-dom'
import { ProForm, ProFormText } from '@ant-design/pro-components'
import { Alert, Button, Card, Form, Spin } from 'antd'
import { UserOutlined, MailOutlined, LockOutlined } from '@ant-design/icons'
import { register, getAuthConfig, getCurrentUser } from '@/services/auth'
import { useAuthStore } from '@/stores/authStore'
import { getMessageInstance } from '@/utils/messageHolder'
import { APP_TITLE } from '@/utils/constants'
import type { RegisterRequest } from '@/types/auth'
import './index.css'

const registerHighlights = ['统一身份访问', '租户协作空间', '资源治理就绪']
const registerTrustItems = ['密码强度校验', '注册后自动进入平台']

function ProductIcon({ className = '' }: { className?: string }) {
  return <img className={`register-product-icon ${className}`} src="/favicon.svg" alt="" />
}

function validatePassword(_: unknown, value: string) {
  if (!value) return Promise.reject(new Error('请输入密码'))
  const rules = [
    { test: (v: string) => v.length >= 8, label: '至少 8 个字符' },
    { test: (v: string) => /[A-Z]/.test(v), label: '至少 1 个大写字母' },
    { test: (v: string) => /[a-z]/.test(v), label: '至少 1 个小写字母' },
    { test: (v: string) => /\d/.test(v), label: '至少 1 个数字' },
  ]
  const failed = rules.find((r) => !r.test(value))
  if (failed) return Promise.reject(new Error(`密码需满足: ${failed.label}`))
  return Promise.resolve()
}

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const [configLoading, setConfigLoading] = useState(true)
  const [allowUserRegistration, setAllowUserRegistration] = useState(false)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const setTokens = useAuthStore((s) => s.setTokens)
  const authLogin = useAuthStore((s) => s.login)
  const [form] = Form.useForm()

  useEffect(() => {
    let mounted = true
    getAuthConfig()
      .then((res) => {
        if (mounted) {
          setAllowUserRegistration(Boolean(res.data?.allowUserRegistration))
        }
      })
      .catch(() => {
        if (mounted) {
          setAllowUserRegistration(false)
        }
      })
      .finally(() => {
        if (mounted) {
          setConfigLoading(false)
        }
      })
    return () => {
      mounted = false
    }
  }, [])

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  const handleSubmit = async (values: RegisterRequest) => {
    if (!allowUserRegistration) {
      getMessageInstance()?.warning('当前未开放自助注册，请联系平台管理员')
      return
    }

    setLoading(true)
    try {
      const res = await register(values)
      if (res.success && res.data) {
        setTokens(res.data.accessToken, res.data.refreshToken)
        const userRes = await getCurrentUser()
        if (userRes.success && userRes.data) {
          authLogin(userRes.data, res.data.accessToken, res.data.refreshToken)
        } else {
          getMessageInstance()?.error('获取用户信息失败')
          return
        }
        getMessageInstance()?.success('注册成功')
        const redirect = searchParams.get('redirect') || '/dashboard'
        navigate(redirect, { replace: true })
      }
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { message?: string } } }
      const status = error.response?.status
      const msg = error.response?.data?.message
      if (status === 409) {
        getMessageInstance()?.error(msg || '用户名或邮箱已存在')
      } else {
        getMessageInstance()?.error(msg || '注册失败, 请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="register-page">
      <div className="register-background" aria-hidden="true">
        <div className="register-scanline" />
        <div className="register-circuit register-circuit-left" />
        <div className="register-circuit register-circuit-right" />
      </div>

      <main className="register-shell">
        <section className="register-brand-panel">
          <div className="register-product-mark">
            <ProductIcon className="register-logo-mark" />
            <span>{APP_TITLE}</span>
          </div>

          <div className="register-hero-copy">
            <div className="register-eyebrow">
              <ProductIcon className="register-eyebrow-icon" />
              创建 AI 工程账号
            </div>
            <h1>加入 {APP_TITLE} 工作空间</h1>
            <p>用统一账号访问数据、训练、模型与推理服务，在可治理的资源池中协作交付。</p>
          </div>

          <div className="register-highlights" aria-label="注册后能力">
            {registerHighlights.map((item) => (
              <div className="register-highlight" key={item}>
                <ProductIcon className="register-highlight-icon" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="register-form-panel">
          <Card className="register-card elevated-card" bordered={false}>
            <div className="register-card-header">
              <ProductIcon className="register-card-icon" />
              <div>
                <h2>创建账号</h2>
                <p>注册后进入 {APP_TITLE} 控制台</p>
              </div>
            </div>

            <div className="register-trust-row">
              {registerTrustItems.map((item) => (
                <span key={item}>
                  <ProductIcon className="register-trust-icon" />
                  {item}
                </span>
              ))}
            </div>

            {configLoading ? (
              <div className="register-config-loading">
                <Spin />
                <span>正在检查注册开放状态...</span>
              </div>
            ) : allowUserRegistration ? (
              <ProForm<RegisterRequest>
                className="register-form"
                form={form}
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
                      icon={<ProductIcon className="register-button-icon" />}
                      className="register-submit-button"
                    >
                      创建并进入平台
                    </Button>
                  ),
                }}
              >
                <ProFormText
                  name="username"
                  label="用户名"
                  placeholder="请输入用户名"
                  rules={[{ required: true, message: '请输入用户名' }]}
                  fieldProps={{ prefix: <UserOutlined />, maxLength: 50, size: 'large' }}
                />
                <ProFormText
                  name="email"
                  label="邮箱"
                  placeholder="请输入邮箱"
                  rules={[
                    { required: true, message: '请输入邮箱' },
                    { type: 'email', message: '请输入有效的邮箱地址' },
                  ]}
                  fieldProps={{ prefix: <MailOutlined />, size: 'large' }}
                />
                <ProFormText.Password
                  name="password"
                  label="密码"
                  placeholder="请输入密码"
                  rules={[{ required: true, validator: validatePassword }]}
                  fieldProps={{ prefix: <LockOutlined />, size: 'large' }}
                  extra="至少 8 个字符，包含大写字母、小写字母和数字"
                />
                <ProFormText.Password
                  name="confirmPassword"
                  label="确认密码"
                  placeholder="请再次输入密码"
                  dependencies={['password']}
                  rules={[
                    { required: true, message: '请确认密码' },
                    ({ getFieldValue }) => ({
                      validator(_: unknown, value: string) {
                        if (!value || getFieldValue('password') === value) {
                          return Promise.resolve()
                        }
                        return Promise.reject(new Error('两次输入的密码不一致'))
                      },
                    }),
                  ]}
                  fieldProps={{ prefix: <LockOutlined />, size: 'large' }}
                />
              </ProForm>
            ) : (
              <div className="register-disabled-state">
                <Alert
                  type="warning"
                  showIcon
                  message="当前未开放自助注册"
                  description="请联系平台管理员创建账号，或使用已分配的账号登录控制台。"
                />
                <Button block size="large" type="primary" onClick={() => navigate('/login')}>
                  返回登录
                </Button>
              </div>
            )}

            <div className="register-login-link">
              已有账号？
              <Link to="/login">去登录</Link>
            </div>
          </Card>
        </section>
      </main>
    </div>
  )
}
