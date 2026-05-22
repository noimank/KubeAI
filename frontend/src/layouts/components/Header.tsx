import { useNavigate } from 'react-router-dom'
import { Space, Avatar, Dropdown, Tooltip } from 'antd'
import type { CSSProperties, ReactNode } from 'react'
import {
  SearchOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { useNotificationStore } from '@/stores/notificationStore'
import { NotificationDropdown } from './NotificationDropdown'
import { getMessageInstance } from '@/utils/messageHolder'

const actionGroupStyle: CSSProperties = {
  height: '100%',
  display: 'inline-flex',
  alignItems: 'center',
}

const actionButtonStyle: CSSProperties = {
  width: 32,
  height: 32,
  padding: 0,
  border: 0,
  background: 'transparent',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: 6,
  color: 'inherit',
  cursor: 'pointer',
  fontSize: 16,
  lineHeight: 1,
}

function HeaderAction({
  title,
  children,
  onClick,
}: {
  title: string
  children: ReactNode
  onClick?: () => void
}) {
  return (
    <Tooltip title={title}>
      <button type="button" aria-label={title} onClick={onClick} style={actionButtonStyle}>
        {children}
      </button>
    </Tooltip>
  )
}

export function Header() {
  const navigate = useNavigate()
  const logout = useAuthStore((state) => state.logout)
  const themeMode = useThemeStore((s) => s.themeMode)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)
  const unreadCount = useNotificationStore((s) => s.unreadCount)
  const fetchUnreadCount = useNotificationStore((s) => s.fetchUnreadCount)

  useQuery({
    queryKey: ['unreadCount'],
    queryFn: async () => {
      await fetchUnreadCount()
      return null
    },
    refetchInterval: 60_000,
  })

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      logout()
      getMessageInstance()?.success('已退出登录')
      navigate('/login')
    }
  }

  const userMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <UserOutlined />, label: '个人设置' },
    { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
  ]

  return (
    <Space size={8} style={actionGroupStyle}>
      <HeaderAction
        title={themeMode === 'light' ? '切换深色主题' : '切换浅色主题'}
        onClick={toggleTheme}
      >
        {themeMode === 'light' ? <MoonOutlined /> : <SunOutlined />}
      </HeaderAction>
      <HeaderAction title="搜索">
        <SearchOutlined />
      </HeaderAction>
      <NotificationDropdown unreadCount={unreadCount} />
      <Dropdown menu={{ items: userMenuItems, onClick: handleMenuClick }} placement="bottomRight">
        <button type="button" aria-label="用户菜单" style={actionButtonStyle}>
          <Avatar size={28} icon={<UserOutlined />} />
        </button>
      </Dropdown>
    </Space>
  )
}
