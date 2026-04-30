import { Card, Typography } from 'antd'

export default function DashboardPage() {
  return (
    <div>
      <Typography.Title level={3} style={{ marginBottom: 24 }}>
        工作台
      </Typography.Title>
      <Card>
        <Typography.Paragraph type="secondary">
          欢迎使用 KubeAI 平台。请从左侧菜单选择功能模块开始使用。
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
