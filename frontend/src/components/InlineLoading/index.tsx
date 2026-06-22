import { Spin } from 'antd'
import './index.css'

interface InlineLoadingProps {
  tip?: string
}

export default function InlineLoading({ tip }: InlineLoadingProps) {
  return (
    <div className="inline-loading">
      <Spin />
      {tip && <span className="inline-loading-text">{tip}</span>}
    </div>
  )
}
