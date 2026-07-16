import { type ReactNode } from 'react'
import { Typography, Collapse } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { ConfigNode } from '../utils/parseLabelConfig'
import { cssStringToObject, toControlConfig, toObjectConfig } from '../utils/parseLabelConfig'
import type { AnnotationRegion, ImageDimensions } from '../hooks/useAnnotationRegions'
import ChoicesAnnotator from './ChoicesAnnotator'
import TextAreaAnnotator from './TextAreaAnnotator'
import FormControlAnnotator from './FormControlAnnotator'
import { appendAuthToken } from '@/utils/constants'

// ── Workspace context passed through to annotator components ───────────────────

export interface WorkspaceContext {
  task: AnnotationTask
  readOnly: boolean
  submitting: boolean
  regions: AnnotationRegion[]
  selectedRegionId: string | null
  imageDimensions: ImageDimensions | null
  globalResults: Record<string, AnnotationResultItem[]>
  onPerRegionResult: (
    controlName: string,
  ) => (regionId: string, result: AnnotationResultItem | null) => void
  onGlobalResult: (controlName: string) => (results: AnnotationResultItem[]) => void
  getRegionResult: (regionId: string, controlName: string) => AnnotationResultItem | null
  hasSpatialControls: boolean
  /** name → object node 映射，用于分类控件解析引用对象 */
  objectMap: Map<string, ConfigNode>
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

function open(attrs: Record<string, string>): boolean {
  return attrs.open === 'true'
}

function getImageUrl(node: ConfigNode, ctx: WorkspaceContext): string | undefined {
  const field = node.field
  if (!field) return undefined
  return ctx.task.data?.[field] as string | undefined
}

function getTextContent(node: ConfigNode, ctx: WorkspaceContext): string | undefined {
  const field = node.field
  if (!field) return undefined
  const val = ctx.task.data?.[field]
  return typeof val === 'string' ? val : undefined
}

function renderClassification(tag: string, node: ConfigNode, ctx: WorkspaceContext) {
  const controlConfig = toControlConfig(node)
  const perRegion = node.attrs.perregion === 'true'
  const labels = (node.choices ?? []).map((c) => c.value)
  const selRegion = ctx.selectedRegionId
    ? (ctx.regions.find((r) => r.id === ctx.selectedRegionId) ?? null)
    : null
  const curResult = selRegion ? ctx.getRegionResult(selRegion.id, node.name!) : null

  // Resolve the referenced object node for preview / imageUrl
  const objectNode = ctx.objectMap.get(controlConfig.toName)
  const objectConfig = objectNode ? toObjectConfig(objectNode) : undefined
  const objectValue = objectConfig
    ? (ctx.task.data?.[objectConfig.field] as string | undefined)
    : undefined
  const imgUrl = objectConfig?.tag === 'Image' ? objectValue : undefined

  const container = (children: ReactNode) => {
    if (!perRegion) return <div style={{ marginBottom: 12 }}>{children}</div>
    return (
      <div style={{ marginBottom: 12 }}>
        <div
          style={{
            padding: '8px 12px',
            marginBottom: 8,
            borderRadius: 6,
            background: 'var(--ant-color-fill-tertiary)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span style={{ fontWeight: 500, fontSize: 13 }}>{tag}</span>
          <span
            style={{
              fontSize: 12,
              padding: '0 6px',
              borderRadius: 4,
              color: ctx.selectedRegionId ? '#1677ff' : '#999',
              background: ctx.selectedRegionId ? '#e6f4ff' : '#f5f5f5',
            }}
          >
            {ctx.selectedRegionId ? '已选中区域' : '等待选择'}
          </span>
        </div>
        {children}
      </div>
    )
  }

  switch (tag) {
    case 'Choices':
      return container(
        <ChoicesAnnotator
          task={ctx.task}
          labels={labels}
          objectConfig={objectConfig}
          controlConfig={controlConfig}
          readOnly={ctx.readOnly}
          perRegion={perRegion}
          selectedRegionId={perRegion ? ctx.selectedRegionId : null}
          currentRegionChoices={
            perRegion ? ((curResult?.value?.choices as string[] | undefined) ?? null) : null
          }
          onPerRegionResult={perRegion ? ctx.onPerRegionResult(node.name!) : undefined}
          onSubmit={perRegion ? () => {} : ctx.onGlobalResult(node.name!)}
          submitting={ctx.submitting}
          selectedRegion={perRegion ? selRegion : null}
          imageDimensions={perRegion ? ctx.imageDimensions : null}
          imageUrl={perRegion ? imgUrl : undefined}
        />,
      )

    case 'TextArea':
      return container(
        <TextAreaAnnotator
          task={ctx.task}
          labels={labels}
          objectConfig={objectConfig}
          controlConfig={controlConfig}
          readOnly={ctx.readOnly}
          perRegion={perRegion}
          selectedRegionId={perRegion ? ctx.selectedRegionId : null}
          currentRegionText={
            perRegion ? ((curResult?.value?.text as string[] | undefined)?.[0] ?? null) : null
          }
          onPerRegionResult={perRegion ? ctx.onPerRegionResult(node.name!) : undefined}
          onSubmit={perRegion ? () => {} : ctx.onGlobalResult(node.name!)}
          submitting={ctx.submitting}
          selectedRegion={perRegion ? selRegion : null}
          imageDimensions={perRegion ? ctx.imageDimensions : null}
          imageUrl={perRegion ? imgUrl : undefined}
        />,
      )

    case 'Rating':
    case 'Number':
    case 'Taxonomy':
      return container(
        <FormControlAnnotator
          task={ctx.task}
          labels={labels}
          objectConfig={objectConfig}
          controlConfig={controlConfig}
          readOnly={ctx.readOnly}
          perRegion={perRegion}
          selectedRegionId={perRegion ? ctx.selectedRegionId : null}
          currentRegionValue={perRegion ? (curResult?.value ?? null) : null}
          onPerRegionResult={perRegion ? ctx.onPerRegionResult(node.name!) : undefined}
          onSubmit={perRegion ? () => {} : ctx.onGlobalResult(node.name!)}
          submitting={ctx.submitting}
          selectedRegion={perRegion ? selRegion : null}
          imageDimensions={perRegion ? ctx.imageDimensions : null}
          imageUrl={perRegion ? imgUrl : undefined}
        />,
      )

    default:
      return null
  }
}

// ── Recursive renderer ────────────────────────────────────────────────────────

export default function ConfigRenderer({
  node,
  context,
}: {
  node: ConfigNode
  context: WorkspaceContext
}): ReactNode {
  const { attrs, children, text, tag } = node

  switch (tag) {
    // ── Visual ──────────────────────────────────────────────────────────────
    case 'View': {
      const style = attrs.style ? cssStringToObject(attrs.style) : undefined
      if (attrs.display === 'inline') {
        return (
          <span
            id={attrs.idattr}
            className={attrs.classname}
            style={{ display: 'inline-block', marginRight: 15, ...style }}
          >
            {children.map((c) => (
              <ConfigRenderer key={c.name ?? c.tag} node={c} context={context} />
            ))}
          </span>
        )
      }
      return (
        <div id={attrs.idattr} className={attrs.classname} style={style}>
          {children.map((c) => (
            <ConfigRenderer key={c.name ?? c.tag} node={c} context={context} />
          ))}
        </div>
      )
    }

    case 'Header': {
      const size = clamp(Number(attrs.size) || 4, 1, 5) as 1 | 2 | 3 | 4 | 5
      const style = attrs.style ? cssStringToObject(attrs.style) : { margin: '10px 0' }
      const content = attrs.value || text || ''
      return (
        <Typography.Title level={size} style={style} className={attrs.underline ? 'underline' : ''}>
          {content}
        </Typography.Title>
      )
    }

    case 'Markdown': {
      const style = attrs.style ? cssStringToObject(attrs.style) : undefined
      const content = attrs.value || text || ''
      return (
        <div id={attrs.idattr} className={attrs.classname} style={style}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      )
    }

    case 'Style':
      return <style>{text}</style>

    case 'Collapse': {
      const accordion = attrs.accordion !== 'false'
      const bordered = attrs.bordered === 'true'
      const defaultOpen = open(attrs)
      const panels = children.filter((c) => c.tag === 'Panel')
      const defaultActiveKeys = panels
        .filter((p) => (p.attrs.open !== undefined ? open(p.attrs) : defaultOpen))
        .map((_p, i) => `panel-${i}`)
      return (
        <Collapse
          bordered={bordered}
          accordion={accordion}
          defaultActiveKey={accordion ? (defaultActiveKeys[0] ?? []) : defaultActiveKeys}
        >
          {panels.map((panel, i) => (
            <Collapse.Panel
              key={`panel-${i}`}
              header={panel.attrs.value || panel.text || `Panel ${i + 1}`}
            >
              {panel.children.map((c) => (
                <ConfigRenderer key={c.name ?? c.tag} node={c} context={context} />
              ))}
            </Collapse.Panel>
          ))}
        </Collapse>
      )
    }

    // ── Object (data preview — only when no spatial controls in canvas) ───
    case 'Image': {
      if (context.hasSpatialControls) return null
      const imgUrl = getImageUrl(node, context)
      return imgUrl ? (
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <img src={appendAuthToken(imgUrl)} style={{ maxHeight: 400, maxWidth: '100%' }} alt="" />
        </div>
      ) : null
    }

    case 'Text':
    case 'HyperText': {
      if (context.hasSpatialControls) return null
      const content = getTextContent(node, context)
      return content ? (
        <div style={{ marginBottom: 16 }}>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {content}
          </Typography.Paragraph>
        </div>
      ) : null
    }

    // ── Classification controls ────────────────────────────────────────────
    case 'Choices':
    case 'TextArea':
    case 'Rating':
    case 'Number':
    case 'Taxonomy':
      return renderClassification(tag, node, context)

    // ── Spatial / Relation → rendered by canvas, skip ─────────────────────
    case 'Rectangle':
    case 'RectangleLabels':
    case 'Polygon':
    case 'PolygonLabels':
    case 'KeyPoint':
    case 'KeyPointLabels':
    case 'Ellipse':
    case 'EllipseLabels':
    case 'Brush':
    case 'BrushLabels':
    case 'Labels':
    case 'Relation':
    case 'RelationLabels':
      return null

    // ── Unknown ───────────────────────────────────────────────────────────
    default:
      if (children.length > 0) {
        return (
          <>
            {children.map((c) => (
              <ConfigRenderer key={c.name ?? c.tag} node={c} context={context} />
            ))}
          </>
        )
      }
      return null
  }
}
