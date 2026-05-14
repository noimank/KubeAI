import { Link } from 'react-router-dom'
import { Tooltip } from 'antd'
import './index.css'

export interface LineageNode {
  type: 'dataset' | 'training' | 'model' | 'inference'
  label: string
  subLabel?: string
  link?: string
  status: 'completed' | 'pending'
}

interface LineageFlowProps {
  nodes: LineageNode[]
}

const NODE_ICONS: Record<LineageNode['type'], string> = {
  dataset: '📊',
  training: '🔧',
  model: '📦',
  inference: '🚀',
}

function NodeCard({ node }: { node: LineageNode }) {
  const icon = NODE_ICONS[node.type]
  const statusClass = `status-${node.status}`
  const typeClass = node.type
  const clickable = node.status === 'completed' && node.link

  const content = (
    <div
      className={`lineage-node-card ${statusClass} ${typeClass} ${clickable ? 'clickable' : ''}`}
    >
      <span className="lineage-node-icon">{icon}</span>
      <span className="lineage-node-label">{node.label}</span>
      {node.subLabel && <span className="lineage-node-sub-label">{node.subLabel}</span>}
    </div>
  )

  if (node.status === 'pending') {
    return (
      <Tooltip title="功能开发中">
        <div>{content}</div>
      </Tooltip>
    )
  }

  if (node.link) {
    return (
      <Link to={node.link} style={{ textDecoration: 'none', color: 'inherit' }}>
        {content}
      </Link>
    )
  }

  return content
}

export default function LineageFlow({ nodes }: LineageFlowProps) {
  return (
    <div className="lineage-flow">
      {nodes.map((node, idx) => (
        <div key={node.type} className="lineage-node">
          <NodeCard node={node} />
          {idx < nodes.length - 1 && (
            <div className={`lineage-arrow ${node.status === 'completed' ? 'status-active' : ''}`}>
              →
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
