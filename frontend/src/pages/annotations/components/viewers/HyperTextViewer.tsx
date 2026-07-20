import DOMPurify from 'dompurify'
import { Card, Typography } from 'antd'

/**
 * HyperText 对象查看器 —— 将 HTML 数据消毒后渲染。
 * 必须经过 DOMPurify 消毒，禁止裸 dangerouslySetInnerHTML（防 XSS）。
 */
export default function HyperTextViewer({ value }: { value: unknown }) {
  const html = typeof value === 'string' ? value : ''
  if (!html) {
    return <Typography.Text type="secondary">无内容</Typography.Text>
  }
  return (
    <Card size="small" style={{ marginBottom: 16 }}>
      <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }} />
    </Card>
  )
}
