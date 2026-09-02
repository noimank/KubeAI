import { useEffect } from 'react'
import { Avatar, Dropdown } from 'antd'
import type { CSSProperties } from 'react'
import { UserOutlined, LogoutOutlined } from '@ant-design/icons'
import type { MenuProps } from 'antd'

import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { NotificationDropdown } from './NotificationDropdown'
import { getMessageInstance } from '@/utils/messageHolder'

const headerActionsStyle: CSSProperties = {
  height: '100%',
  display: 'flex',
  alignItems: 'center',
  gap: 4,
}

const userButtonStyle: CSSProperties = {
  height: 32,
  padding: '0 8px',
  border: 0,
  background: 'transparent',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: 6,
  color: 'var(--ant-color-text)',
  cursor: 'pointer',
  fontSize: 16,
  lineHeight: 1,
  gap: 8,
  flexShrink: 0,
}

export function Header() {
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)
  const user = useAuthStore((state) => state.user)
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount)

  useEffect(() => {
    fetchUnreadCount()
  }, [fetchUnreadCount])

  const displayName = user?.nickname || user?.username

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'profile') {
      navigate('/profile')
    } else if (key === 'logout') {
      logout()
      getMessageInstance()?.success('已退出登录')
      navigate('/login')
    }
  }

  const userMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <UserOutlined />, label: '个人设置' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
  ]

  return (
    <div style={headerActionsStyle}>
      <NotificationDropdown unreadCount={unreadCount} />
      <Dropdown menu={{ items: userMenuItems, onClick: handleMenuClick }} placement="bottomRight">
        <button type="button" aria-label="用户菜单" style={userButtonStyle}>
          {user?.avatar ? (
            <Avatar size={28} src={user.avatar} />
          ) : (
            <Avatar
              size={28}
              style={{ backgroundColor: '#1890ff', fontSize: 12, verticalAlign: 'middle' }}
            >
              {displayName ? displayName.charAt(0).toUpperCase() : <UserOutlined />}
            </Avatar>
          )}
          {displayName && <span style={{ fontSize: 13, whiteSpace: 'nowrap' }}>{displayName}</span>}
        </button>
      </Dropdown>
    </div>
  )
}
