import { Result } from 'antd'

/** 暂未支持的控件/对象的统一占位 —— 绝不静默渲染 null，向用户明确说明 */
export default function UnsupportedTag({ tag }: { tag: string }) {
  return (
    <Result
      status="warning"
      style={{ padding: '12px 16px', marginBottom: 12 }}
      title={<span style={{ fontSize: 14 }}>控件 {tag} 暂未支持</span>}
      subTitle={
        <span style={{ fontSize: 12 }}>
          该控件类型暂未实现交互，配置已保留，可正常提交其余标注。
        </span>
      }
    />
  )
}
