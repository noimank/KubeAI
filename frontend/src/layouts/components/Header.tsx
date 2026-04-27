import { Space, Avatar, Badge, Dropdown } from 'antd'
import {
  SearchOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { MenuProps } from 'antd'

const userMenuItems: MenuProps['items'] = [
  { key: 'profile', icon: <UserOutlined />, label: '个人设置' },
  { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
  { type: 'divider' },
  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录' },
]

export function Header() {
  return (
    <Space size="middle" style={{ cursor: 'pointer' }}>
      <SearchOutlined style={{ fontSize: 16 }} />
      <Badge count={0} showZero={false}>
        <BellOutlined style={{ fontSize: 16 }} />
      </Badge>
      <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
        <Avatar icon={<UserOutlined />} style={{ cursor: 'pointer' }} />
      </Dropdown>
    </Space>
  )
}
