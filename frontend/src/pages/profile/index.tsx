import { useState, useMemo } from 'react'
import {
  Avatar,
  Button,
  Form,
  Input,
  Tabs,
  Typography,
  Upload,
  message,
  type TabsProps,
} from 'antd'
import {
  UserOutlined,
  CameraOutlined,
  LockOutlined,
  MailOutlined,
  SafetyCertificateOutlined,
  InfoCircleOutlined,
  IdcardOutlined,
  CheckCircleFilled,
} from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { updateProfile, uploadAvatar, changePassword } from '@/services/profile'
import type { User } from '@/types/auth'

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const MAX_SIZE = 2 * 1024 * 1024

const ROLE_LABELS: Record<string, string> = {
  admin: '系统管理员',
  mlops: 'MLOps 工程师',
  engineer: '算法工程师',
  annotator: '数据标注员',
}

function getInitial(name?: string): string {
  if (!name) return ''
  return name.charAt(0).toUpperCase()
}

function DefaultAvatar({ name, size = 96 }: { name?: string; size?: number }) {
  const initial = getInitial(name)
  return (
    <Avatar
      size={size}
      style={{
        background: 'linear-gradient(135deg, #1890ff 0%, #40a9ff 100%)',
        verticalAlign: 'middle',
        fontSize: size * 0.38,
        fontWeight: 600,
        fontFamily: '"DM Sans", "Noto Sans SC", -apple-system, BlinkMacSystemFont, sans-serif',
      }}
    >
      {initial || <UserOutlined />}
    </Avatar>
  )
}

// --- Password strength indicator ---
function getPasswordStrength(password: string): {
  level: number
  label: string
  color: string
} {
  if (!password) return { level: 0, label: '', color: '' }
  let score = 0
  if (password.length >= 8) score++
  if (password.length >= 12) score++
  if (/[A-Z]/.test(password)) score++
  if (/[a-z]/.test(password)) score++
  if (/\d/.test(password)) score++
  if (/[^A-Za-z0-9]/.test(password)) score++

  if (score <= 2) return { level: 1, label: '弱', color: '#ff4d4f' }
  if (score <= 4) return { level: 2, label: '中', color: '#faad14' }
  return { level: 3, label: '强', color: '#52c41a' }
}

function PasswordStrengthBar({ password }: { password: string }) {
  const strength = useMemo(() => getPasswordStrength(password), [password])
  if (!password) return null

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginTop: -4,
        marginBottom: 4,
      }}
    >
      <div style={{ display: 'flex', gap: 3 }}>
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              width: 40,
              height: 3,
              borderRadius: 2,
              background: i <= strength.level ? strength.color : 'rgba(128,128,128,0.15)',
              transition: 'background 0.3s ease',
            }}
          />
        ))}
      </div>
      <span style={{ fontSize: 12, color: strength.color, fontWeight: 500 }}>{strength.label}</span>
    </div>
  )
}

// --- Info row for profile banner ---
function InfoPill({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 14px',
        borderRadius: 8,
        background: 'rgba(255, 255, 255, 0.06)',
        backdropFilter: 'blur(4px)',
        border: '1px solid rgba(255, 255, 255, 0.08)',
      }}
    >
      <span style={{ fontSize: 14, opacity: 0.7 }}>{icon}</span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        <span
          style={{
            fontSize: 11,
            opacity: 0.5,
            lineHeight: 1,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          {label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.3 }}>{value}</span>
      </div>
    </div>
  )
}

// --- Inline notice banner ---
function InfoBanner({
  icon,
  tone = 'info',
  children,
}: {
  icon: React.ReactNode
  tone?: 'info' | 'warning'
  children: React.ReactNode
}) {
  const palette =
    tone === 'warning'
      ? {
          background: 'rgba(250,173,20,0.04)',
          border: 'rgba(250,173,20,0.08)',
          color: '#faad14',
        }
      : {
          background: 'rgba(24,144,255,0.04)',
          border: 'rgba(24,144,255,0.08)',
          color: '#1890ff',
        }
  return (
    <div
      style={{
        padding: '14px 18px',
        borderRadius: 8,
        background: palette.background,
        border: `1px solid ${palette.border}`,
        marginBottom: 28,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}
    >
      <span style={{ fontSize: 16, color: palette.color, flexShrink: 0 }}>{icon}</span>
      <span
        style={{
          fontSize: 13,
          color: 'rgba(0,0,0,0.55)',
          lineHeight: 1.5,
        }}
      >
        {children}
      </span>
    </div>
  )
}

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)

  const [profileForm] = Form.useForm()
  const [passwordForm] = Form.useForm()
  const [profileSubmitting, setProfileSubmitting] = useState(false)
  const [passwordSubmitting, setPasswordSubmitting] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [activeTab, setActiveTab] = useState('profile')

  const displayName = user?.nickname || user?.username
  // 第三方登录账号的资料与凭证由身份提供方管理, 个人设置仅作展示
  const isExternalUser = !!user?.authProvider && user.authProvider !== 'local'

  const handleAvatarUpload = async (file: File) => {
    if (!ALLOWED_TYPES.includes(file.type)) {
      message.error('仅支持 JPEG、PNG、GIF、WebP 格式的图片')
      return
    }
    if (file.size > MAX_SIZE) {
      message.error('头像文件大小不能超过 2MB')
      return
    }
    try {
      const res = await uploadAvatar(file)
      if (res.data) {
        setUser(res.data as User)
        message.success('头像上传成功')
      }
    } catch {
      message.error('头像上传失败')
    }
  }

  const handleProfileSubmit = async (values: { nickname?: string; email?: string }) => {
    try {
      setProfileSubmitting(true)
      const res = await updateProfile(values)
      if (res.data) {
        setUser(res.data as User)
        message.success('个人信息更新成功')
      }
    } catch {
      message.error('更新失败')
    } finally {
      setProfileSubmitting(false)
    }
  }

  const handlePasswordSubmit = async (values: {
    currentPassword: string
    newPassword: string
    confirmPassword: string
  }) => {
    try {
      setPasswordSubmitting(true)
      await changePassword(values)
      message.success('密码修改成功')
      passwordForm.resetFields()
      setNewPassword('')
    } catch {
      message.error('密码修改失败')
    } finally {
      setPasswordSubmitting(false)
    }
  }

  const avatarFrame = (
    <div
      style={{
        position: 'relative',
        cursor: isExternalUser ? 'default' : 'pointer',
        flexShrink: 0,
        borderRadius: '50%',
        padding: 3,
        background: 'linear-gradient(135deg, rgba(24,144,255,0.5), rgba(64,169,255,0.3))',
      }}
    >
      {user?.avatar ? (
        // 纯内网部署下外部头像 URL（如 IdP 默认头像）不可达，加载失败时回退首字母
        <Avatar
          size={96}
          src={user.avatar}
          onError={() => true}
          style={{
            border: '3px solid #e8f0fe',
          }}
        >
          {displayName?.charAt(0).toUpperCase()}
        </Avatar>
      ) : (
        <DefaultAvatar name={displayName} size={96} />
      )}
      {/* Camera overlay (hidden for third-party accounts) */}
      {!isExternalUser && (
        <div
          style={{
            position: 'absolute',
            bottom: 4,
            right: 4,
            width: 30,
            height: 30,
            borderRadius: '50%',
            background: '#ffffff',
            border: '2px solid #dbeafe',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#1890ff',
            fontSize: 13,
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            transition: 'transform 0.2s ease',
          }}
        >
          <CameraOutlined />
        </div>
      )}
    </div>
  )

  const tabItems: TabsProps['items'] = [
    {
      key: 'profile',
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <IdcardOutlined />
          基本信息
        </span>
      ),
      children: (
        <div
          style={{
            maxWidth: 560,
            padding: '8px 0 0',
          }}
        >
          {isExternalUser && (
            <InfoBanner icon={<InfoCircleOutlined />}>
              当前账号通过第三方登录，基本信息由身份提供方统一管理，此处仅作展示。如需变更，请联系身份提供方或系统管理员。
            </InfoBanner>
          )}
          <Form
            form={profileForm}
            layout="vertical"
            initialValues={{
              nickname: user?.nickname || '',
              email: user?.email || '',
            }}
            onFinish={handleProfileSubmit}
            requiredMark={false}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '0 24px',
              }}
            >
              <Form.Item label="用户名" style={{ marginBottom: 20 }}>
                <Input
                  value={user?.username}
                  disabled
                  style={{ color: 'rgba(0,0,0,0.45)' }}
                  prefix={<UserOutlined style={{ opacity: 0.4 }} />}
                />
              </Form.Item>
              <Form.Item label="角色" style={{ marginBottom: 20 }}>
                <Input
                  value={ROLE_LABELS[user?.role || ''] || user?.role}
                  disabled
                  style={{ color: 'rgba(0,0,0,0.45)' }}
                  prefix={<SafetyCertificateOutlined style={{ opacity: 0.4 }} />}
                />
              </Form.Item>
            </div>

            <Form.Item
              name="nickname"
              label="昵称"
              style={{ marginBottom: 20 }}
              rules={[{ max: 100, message: '昵称不能超过 100 个字符' }]}
            >
              <Input
                placeholder="给自己起个名字"
                maxLength={100}
                disabled={isExternalUser}
                style={isExternalUser ? { color: 'rgba(0,0,0,0.45)' } : undefined}
              />
            </Form.Item>

            <Form.Item
              name="email"
              label="邮箱"
              style={{ marginBottom: 28 }}
              rules={[
                { required: true, message: '请输入邮箱' },
                { type: 'email', message: '请输入有效的邮箱地址' },
              ]}
            >
              <Input
                placeholder="name@example.com"
                prefix={<MailOutlined style={{ opacity: 0.4 }} />}
                disabled={isExternalUser}
                style={isExternalUser ? { color: 'rgba(0,0,0,0.45)' } : undefined}
              />
            </Form.Item>

            {!isExternalUser && (
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={profileSubmitting}
                  style={{ borderRadius: 6, height: 36, paddingInline: 28 }}
                >
                  保存修改
                </Button>
              </Form.Item>
            )}
          </Form>
        </div>
      ),
    },
    {
      key: 'security',
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          <LockOutlined />
          安全设置
        </span>
      ),
      children: (
        <div
          style={{
            maxWidth: 480,
            padding: '8px 0 0',
          }}
        >
          {isExternalUser ? (
            <InfoBanner icon={<SafetyCertificateOutlined />}>
              您通过第三方账号登录，登录凭证由身份提供方统一管理，无法在此修改密码。如需变更，请联系身份提供方或系统管理员。
            </InfoBanner>
          ) : (
            <>
              <InfoBanner icon={<SafetyCertificateOutlined />}>
                定期更新密码有助于保护您的账户安全。密码需包含大小写字母和数字，至少 8 个字符。
              </InfoBanner>

              <Form
                form={passwordForm}
                layout="vertical"
                onFinish={handlePasswordSubmit}
                requiredMark={false}
              >
                <Form.Item
                  name="currentPassword"
                  label="当前密码"
                  style={{ marginBottom: 20 }}
                  rules={[{ required: true, message: '请输入当前密码' }]}
                >
                  <Input.Password placeholder="请输入当前密码" />
                </Form.Item>
                <Form.Item
                  name="newPassword"
                  label="新密码"
                  style={{ marginBottom: 6 }}
                  rules={[
                    { required: true, message: '请输入新密码' },
                    { min: 8, message: '密码至少 8 个字符' },
                    { pattern: /[A-Z]/, message: '需包含至少一个大写字母' },
                    { pattern: /[a-z]/, message: '需包含至少一个小写字母' },
                    { pattern: /\d/, message: '需包含至少一个数字' },
                  ]}
                >
                  <Input.Password
                    placeholder="请输入新密码"
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                </Form.Item>
                <PasswordStrengthBar password={newPassword} />
                <Form.Item
                  name="confirmPassword"
                  label="确认新密码"
                  style={{ marginBottom: 28 }}
                  dependencies={['newPassword']}
                  rules={[
                    { required: true, message: '请确认新密码' },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue('newPassword') === value) {
                          return Promise.resolve()
                        }
                        return Promise.reject(new Error('两次输入的密码不一致'))
                      },
                    }),
                  ]}
                >
                  <Input.Password placeholder="请再次输入新密码" />
                </Form.Item>
                <Form.Item style={{ marginBottom: 0 }}>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={passwordSubmitting}
                    style={{ borderRadius: 6, height: 36, paddingInline: 28 }}
                  >
                    修改密码
                  </Button>
                </Form.Item>
              </Form>
            </>
          )}
        </div>
      ),
    },
  ]

  return (
    <div style={{ padding: '0 0 32px' }}>
      {/* --- Profile Banner --- */}
      <div
        style={{
          borderRadius: 12,
          overflow: 'hidden',
          marginBottom: 24,
          background: 'linear-gradient(135deg, #e8f0fe 0%, #dbeafe 40%, #f0f5ff 100%)',
          border: '1px solid rgba(24,144,255,0.1)',
          position: 'relative',
        }}
      >
        {/* Decorative circles */}
        <div
          style={{
            position: 'absolute',
            top: -40,
            right: -40,
            width: 200,
            height: 200,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(24,144,255,0.08) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: -60,
            left: '30%',
            width: 160,
            height: 160,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(64,169,255,0.05) 0%, transparent 70%)',
            pointerEvents: 'none',
          }}
        />

        <div
          style={{
            padding: '36px 36px 32px',
            display: 'flex',
            alignItems: 'center',
            gap: 28,
            position: 'relative',
            zIndex: 1,
          }}
        >
          {/* Avatar with upload (third-party accounts are read-only) */}
          {isExternalUser ? (
            avatarFrame
          ) : (
            <Upload
              showUploadList={false}
              accept="image/jpeg,image/png,image/gif,image/webp"
              beforeUpload={(file) => {
                handleAvatarUpload(file)
                return false
              }}
            >
              {avatarFrame}
            </Upload>
          )}

          {/* User info */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: 12,
            }}
          >
            <div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  marginBottom: 6,
                }}
              >
                <Typography.Title
                  level={3}
                  style={{
                    margin: 0,
                    color: 'rgba(0,0,0,0.88)',
                    fontWeight: 600,
                    fontSize: 24,
                  }}
                >
                  {displayName || user?.username}
                </Typography.Title>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '2px 10px',
                    borderRadius: 12,
                    fontSize: 12,
                    fontWeight: 500,
                    background: 'rgba(24,144,255,0.1)',
                    color: '#1890ff',
                    border: '1px solid rgba(24,144,255,0.15)',
                  }}
                >
                  <CheckCircleFilled style={{ fontSize: 10 }} />
                  {ROLE_LABELS[user?.role || ''] || user?.role}
                </span>
              </div>
              {user?.nickname && user.nickname !== user.username && (
                <Typography.Text
                  style={{
                    fontSize: 13,
                    color: 'rgba(0,0,0,0.35)',
                  }}
                >
                  @{user.username}
                </Typography.Text>
              )}
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                flexWrap: 'wrap',
              }}
            >
              {user?.email && <InfoPill icon={<MailOutlined />} label="邮箱" value={user.email} />}
              <InfoPill icon={<IdcardOutlined />} label="用户名" value={user?.username || '—'} />
            </div>
          </div>
        </div>
      </div>

      {/* --- Tabs section --- */}
      <div
        style={{
          borderRadius: 12,
          background: '#ffffff',
          border: '1px solid rgba(0,0,0,0.06)',
          overflow: 'hidden',
        }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={tabItems}
          style={{ padding: '0 24px' }}
          tabBarStyle={{ marginBottom: 0, padding: '4px 0 0' }}
        />
      </div>
    </div>
  )
}
