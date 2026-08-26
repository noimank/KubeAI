import { Image, List, Tag, Typography } from 'antd'

/**
 * List 对象查看器 —— 渲染数组数据源（Ranker 的输入）。
 * 数组项支持：字符串、{ image/url } 图片对象、其他对象（展示键值）。
 */
export default function ListViewer({ value, title }: { value: unknown; title?: string }) {
  const items = Array.isArray(value) ? value : []
  if (items.length === 0) {
    return <Typography.Text type="secondary">无列表数据</Typography.Text>
  }

  return (
    <div>
      {title && (
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
          {title}
        </Typography.Text>
      )}
      <List
        size="small"
        bordered
        dataSource={items}
        renderItem={(item, idx) => {
          const img = imageUrlOf(item)
          return (
            <List.Item>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
                <Tag>{idx + 1}</Tag>
                {img ? (
                  <Image src={img} style={{ maxHeight: 80 }} alt="" />
                ) : (
                  <Typography.Text style={{ wordBreak: 'break-all' }}>
                    {typeof item === 'string' ? item : JSON.stringify(item)}
                  </Typography.Text>
                )}
              </div>
            </List.Item>
          )
        }}
      />
    </div>
  )
}

function imageUrlOf(item: unknown): string | undefined {
  if (typeof item === 'object' && item !== null) {
    const obj = item as Record<string, unknown>
    const candidate = (obj.image ?? obj.url ?? obj.src) as unknown
    return typeof candidate === 'string' ? candidate : undefined
  }
  return undefined
}
