import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ProForm, ProFormText } from '@ant-design/pro-components'
import { Card, message, Button, type FormInstance } from 'antd'
import { UserOutlined, MailOutlined, LockOutlined } from '@ant-design/icons'
import { register } from '@/services/auth'
import { useAuthStore } from '@/stores/authStore'
import type { RegisterRequest } from '@/types/auth'

function validatePassword(_: unknown, value: string) {
  if (!value) return Promise.reject(new Error('请输入密码'))
  const rules = [
    { test: (v: string) => v.length >= 8, label: '至少 8 个字符' },
    { test: (v: string) => /[A-Z]/.test(v), label: '至少 1 个大写字母' },
    { test: (v: string) => /[a-z]/.test(v), label: '至少 1 个小写字母' },
    { test: (v: string) => /\d/.test(v), label: '至少 1 个数字' },
  ]
  const failed = rules.find((r) => !r.test(value))
  if (failed) return Promise.reject(new Error(`密码需满足：${failed.label}`))
  return Promise.resolve()
}

export default function RegisterPage() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const authLogin = useAuthStore((s) => s.login)
  const [formRef, setFormRef] = useState<FormInstance | null>(null)

  const handleSubmit = async (values: RegisterRequest) => {
    setLoading(true)
    try {
      const res = await register(values)
      if (res.success && res.data) {
        authLogin(
          { id: '', username: values.username, email: values.email, role: '', tenant_id: '' },
          res.data.access_token,
          res.data.refresh_token,
        )
        message.success('注册成功')
        navigate('/dashboard', { replace: true })
      }
    } catch (err: unknown) {
      const error = err as { response?: { status?: number; data?: { message?: string } } }
      const status = error.response?.status
      const msg = error.response?.data?.message
      if (status === 409) {
        message.error(msg || '用户名或邮箱已存在')
      } else {
        message.error(msg || '注册失败，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card style={{ width: '100%', maxWidth: 600 }}>
      <ProForm<RegisterRequest>
        formRef={setFormRef}
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
              注册
            </Button>
          ),
        }}
      >
        <h2 style={{ textAlign: 'center', marginBottom: 24 }}>注册</h2>
        <ProFormText
          name="username"
          label="用户名"
          placeholder="请输入用户名"
          rules={[{ required: true, message: '请输入用户名' }]}
          fieldProps={{ prefix: <UserOutlined />, maxLength: 50 }}
        />
        <ProFormText
          name="email"
          label="邮箱"
          placeholder="请输入邮箱"
          rules={[
            { required: true, message: '请输入邮箱' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}
          fieldProps={{ prefix: <MailOutlined /> }}
        />
        <ProFormText.Password
          name="password"
          label="密码"
          placeholder="请输入密码"
          rules={[{ required: true, validator: validatePassword }]}
          fieldProps={{ prefix: <LockOutlined /> }}
          extra="密码至少 8 个字符，需包含大写字母、小写字母和数字"
        />
        <ProFormText.Password
          name="confirm_password"
          label="确认密码"
          placeholder="请再次输入密码"
          dependencies={['password']}
          rules={[
            { required: true, message: '请确认密码' },
            () => ({
              validator(_: unknown, value: string) {
                if (!value || (formRef && formRef.getFieldValue('password') === value)) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('两次输入的密码不一致'))
              },
            }),
          ]}
          fieldProps={{ prefix: <LockOutlined /> }}
        />
      </ProForm>
      <div style={{ textAlign: 'center', marginTop: 16 }}>
        <Link to="/login">
          <Button type="link">已有账号？去登录</Button>
        </Link>
      </div>
    </Card>
  )
}
