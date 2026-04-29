import { useNavigate } from 'react-router-dom'
import { App, Space, Avatar, Badge, Dropdown, Tooltip } from 'antd'
import {
  SearchOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  SunOutlined,
  MoonOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'

import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'

export function Header() {
  const navigate = useNavigate()
  const { message } = App.useApp()
  const logout = useAuthStore((state) => state.logout)
  const themeMode = useThemeStore((s) => s.themeMode)
  const toggleTheme = useThemeStore((s) => s.toggleTheme)

  const handleMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') {
      logout()
      message.success('已退出登录')
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
    <Space size="middle" style={{ cursor: 'pointer' }}>
      <Tooltip title={themeMode === 'light' ? '切换深色主题' : '切换浅色主题'}>
        <span
          onClick={toggleTheme}
          style={{ fontSize: 16, display: 'inline-flex', alignItems: 'center' }}
        >
          {themeMode === 'light' ? <MoonOutlined /> : <SunOutlined />}
        </span>
      </Tooltip>
      <SearchOutlined style={{ fontSize: 16 }} />
      <Badge count={0} showZero={false}>
        <BellOutlined style={{ fontSize: 16 }} />
      </Badge>
      <Dropdown menu={{ items: userMenuItems, onClick: handleMenuClick }} placement="bottomRight">
        <Avatar icon={<UserOutlined />} style={{ cursor: 'pointer' }} />
      </Dropdown>
    </Space>
  )
}
