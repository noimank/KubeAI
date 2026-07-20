import { Button, Card, Divider, Space, Tag, Typography } from 'antd'
import type { ConfigNode } from '../utils/parseLabelConfig'
import { toRelationConfig } from '../utils/parseLabelConfig'
import type { Region } from '../hooks/useAnnotationRegions'
import type { AnnotationRelation } from '../hooks/useAnnotationRelations'

interface RelationPanelProps {
  relationControls: ConfigNode[]
  regions: Region[]
  selectedRegionId: string | null
  relations: AnnotationRelation[]
  selectedRelationId: string | null
  readOnly: boolean
  onAddRelation: (rel: AnnotationRelation) => void
  onRemoveRelation: (id: string) => void
}

/**
 * 关系标注侧栏 —— 从 workspace 内联逻辑抽取。
 * 点击区域为源、再点另一区域为目标创建关系；支持 RelationLabels 的标签选择。
 */
export default function RelationPanel({
  relationControls,
  regions,
  selectedRegionId,
  relations,
  readOnly,
  onAddRelation,
  onRemoveRelation,
}: RelationPanelProps) {
  if (relationControls.length === 0) return null

  const regionLabel = (id: string) => regions.find((r) => r.id === id)?.label || '区域'

  return (
    <>
      <Divider style={{ margin: '4px 0' }}>关系标注</Divider>
      {relationControls.map((relNode) => {
        const relConfig = toRelationConfig(relNode)
        return (
          <Card key={relConfig.name} size="small" title={relConfig.tag}>
            {!readOnly && (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  点击左侧区域列表中的一个区域作为源，再点击另一个作为目标来创建关系。
                </Typography.Text>
                {relConfig.choices.length > 0 && !readOnly && (
                  <Space wrap>
                    {relConfig.choices.map((ch) => (
                      <Tag
                        key={ch.value}
                        color="blue"
                        style={{ cursor: 'pointer' }}
                        onClick={() => {
                          if (selectedRegionId) {
                            onAddRelation({
                              id: crypto.randomUUID(),
                              fromRegionId: selectedRegionId,
                              toRegionId: '',
                              label: ch.value,
                              fromName: relConfig.name,
                            })
                          }
                        }}
                      >
                        {ch.value}
                      </Tag>
                    ))}
                  </Space>
                )}
              </Space>
            )}
            {relations.filter((r) => r.fromName === relConfig.name).length > 0 && (
              <div style={{ marginTop: 8 }}>
                {relations
                  .filter((r) => r.fromName === relConfig.name)
                  .map((rel, i) => (
                    <div
                      key={rel.id}
                      style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}
                    >
                      <Tag color="blue">{rel.label || `关系${i + 1}`}</Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        {regionLabel(rel.fromRegionId)} → {regionLabel(rel.toRegionId)}
                      </Typography.Text>
                      {!readOnly && (
                        <Button
                          type="text"
                          size="small"
                          danger
                          onClick={() => onRemoveRelation(rel.id)}
                        >
                          ×
                        </Button>
                      )}
                    </div>
                  ))}
              </div>
            )}
          </Card>
        )
      })}
    </>
  )
}
