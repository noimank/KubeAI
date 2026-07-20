import { type ReactNode } from 'react'
import { Typography, Collapse, Input, Card } from 'antd'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { ConfigNode } from '../utils/parseLabelConfig'
import { cssStringToObject, toControlConfig, toObjectConfig } from '../utils/parseLabelConfig'
import type { LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import type { Region, ImageDimensions } from '../hooks/useAnnotationRegions'
import { controlMode, objectIsCanvas, objectPreview } from '../registry/tags'
import { resolveVisibility, type VisibilityState } from '../utils/visibility'
import ChoicesAnnotator from './ChoicesAnnotator'
import TextAreaAnnotator from './TextAreaAnnotator'
import FormControlAnnotator from './FormControlAnnotator'
import PairwiseAnnotator from './PairwiseAnnotator'
import RankerAnnotator from './RankerAnnotator'
import UnsupportedTag from './UnsupportedTag'
import ListViewer from './viewers/ListViewer'
import HyperTextViewer from './viewers/HyperTextViewer'
import TableView from './viewers/TableView'
import PdfView from './viewers/PdfView'
import TimeSeriesViewer from './viewers/TimeSeriesViewer'
import AudioViewer from './viewers/AudioViewer'
import { appendAuthToken } from '@/utils/constants'

// ── Workspace context passed through to annotator components ───────────────────

export interface WorkspaceContext {
  task: AnnotationTask
  readOnly: boolean
  submitting: boolean
  regions: Region[]
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
  /** 条件可见性求值状态（visibleWhen / whenRole 等） */
  visibility: VisibilityState
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

function open(attrs: Record<string, string>): boolean {
  return attrs.open === 'true'
}

function getObjectFieldUrl(node: ConfigNode, ctx: WorkspaceContext): string | undefined {
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

/** 取 object 字段对应的原始数据（任意类型，供各查看器解释） */
function getObjectData(node: ConfigNode, ctx: WorkspaceContext): unknown {
  const field = node.field
  if (!field) return undefined
  return ctx.task.data?.[field]
}

// ── DOM 控件渲染（Choices/TextArea/Rating/Number/Taxonomy/DateTime/Pairwise）──

function renderDomControl(tag: string, node: ConfigNode, ctx: WorkspaceContext): ReactNode {
  const buildObjectConfigs = () => {
    const objectConfigs = new Map<string, LabelStudioObjectConfig>()
    for (const [name, objNode] of ctx.objectMap) {
      objectConfigs.set(name, toObjectConfig(objNode))
    }
    return objectConfigs
  }

  if (tag === 'Pairwise') {
    const controlConfig = toControlConfig(node)
    return (
      <PairwiseAnnotator
        task={ctx.task}
        objectConfigs={buildObjectConfigs()}
        controlConfig={controlConfig}
        onSubmit={ctx.onGlobalResult(node.name!)}
        submitting={ctx.submitting}
        readOnly={ctx.readOnly}
      />
    )
  }

  if (tag === 'Ranker') {
    const controlConfig = toControlConfig(node)
    return (
      <RankerAnnotator
        task={ctx.task}
        objectConfigs={buildObjectConfigs()}
        controlConfig={controlConfig}
        onSubmit={ctx.onGlobalResult(node.name!)}
        submitting={ctx.submitting}
        readOnly={ctx.readOnly}
      />
    )
  }

  // Choices / TextArea / Rating / Number / Taxonomy / DateTime 共享 perRegion 容器与回显逻辑
  const controlConfig = toControlConfig(node)
  const perRegion = node.attrs.perregion === 'true'
  const labels = (node.choices ?? []).map((c) => c.value)
  const selRegion = ctx.selectedRegionId
    ? (ctx.regions.find((r) => r.id === ctx.selectedRegionId) ?? null)
    : null
  const curResult = selRegion ? ctx.getRegionResult(selRegion.id, node.name!) : null

  const objectNode = ctx.objectMap.get(controlConfig.toName)
  const objectConfig = objectNode ? toObjectConfig(objectNode) : undefined
  const objectValue = objectConfig
    ? (ctx.task.data?.[objectConfig.field] as string | undefined)
    : undefined
  const imgUrl = objectConfig?.tag === 'Image' ? objectValue : undefined

  const wrap = (children: ReactNode) =>
    perRegion ? (
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
    ) : (
      <div style={{ marginBottom: 12 }}>{children}</div>
    )

  const common = {
    task: ctx.task,
    labels,
    objectConfig,
    controlConfig,
    readOnly: ctx.readOnly,
    perRegion,
    selectedRegionId: perRegion ? ctx.selectedRegionId : null,
    onPerRegionResult: perRegion ? ctx.onPerRegionResult(node.name!) : undefined,
    onSubmit: perRegion ? () => {} : ctx.onGlobalResult(node.name!),
    submitting: ctx.submitting,
    selectedRegion: perRegion ? selRegion : null,
    imageDimensions: perRegion ? ctx.imageDimensions : null,
    imageUrl: perRegion ? imgUrl : undefined,
  }

  if (tag === 'Choices') {
    return wrap(
      <ChoicesAnnotator
        {...common}
        currentRegionChoices={
          perRegion ? ((curResult?.value?.choices as string[] | undefined) ?? null) : null
        }
      />,
    )
  }
  if (tag === 'TextArea') {
    return wrap(
      <TextAreaAnnotator
        {...common}
        currentRegionText={
          perRegion ? ((curResult?.value?.text as string[] | undefined)?.[0] ?? null) : null
        }
      />,
    )
  }
  // Rating / Number / Taxonomy / DateTime
  return wrap(
    <FormControlAnnotator
      {...common}
      currentRegionValue={perRegion ? (curResult?.value ?? null) : null}
    />,
  )
}

// ── 对象预览（侧栏；canvas 对象在有空间控件时让位给画布面板）─────────────────

function renderObjectPreview(node: ConfigNode, ctx: WorkspaceContext): ReactNode {
  const tag = node.tag
  if (objectIsCanvas(tag) && ctx.hasSpatialControls) return null

  // 专用查看器（Table/List/PDF）
  if (tag === 'Table') {
    return (
      <div style={{ marginBottom: 16 }}>
        <TableView value={getObjectData(node, ctx)} sep={node.attrs.sep} />
      </div>
    )
  }
  if (tag === 'List') {
    return (
      <div style={{ marginBottom: 16 }}>
        <ListViewer value={getObjectData(node, ctx)} title={node.attrs.title || node.attrs.value} />
      </div>
    )
  }
  if (tag === 'PDF' || tag === 'Pdf') {
    return <PdfView value={getObjectData(node, ctx)} />
  }
  if (tag === 'TimeSeries') {
    return (
      <div style={{ marginBottom: 16 }}>
        <TimeSeriesViewer
          value={getObjectData(node, ctx)}
          channels={node.channels}
          sep={node.attrs.sep}
          timeColumn={node.attrs.timecolumn}
        />
      </div>
    )
  }

  // 通用预览（按 preview kind）
  switch (objectPreview(tag)) {
    case 'image': {
      const url = getObjectFieldUrl(node, ctx)
      return url ? (
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <img src={appendAuthToken(url)} style={{ maxHeight: 400, maxWidth: '100%' }} alt="" />
        </div>
      ) : null
    }
    case 'audio':
      return <AudioViewer value={getObjectFieldUrl(node, ctx)} />
    case 'video': {
      const url = getObjectFieldUrl(node, ctx)
      return url ? (
        <div style={{ marginBottom: 16 }}>
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
            🎬 视频预览
          </Typography.Text>
          <video controls src={appendAuthToken(url)} style={{ maxWidth: '100%', maxHeight: 300 }} />
        </div>
      ) : null
    }
    case 'html':
      return <HyperTextViewer value={getObjectData(node, ctx)} />
    case 'text': {
      const content = getTextContent(node, ctx)
      return content ? (
        <div style={{ marginBottom: 16 }}>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {content}
          </Typography.Paragraph>
        </div>
      ) : null
    }
    case 'none':
    default:
      // PagedView / TimeSeries 等暂以占位提示，后续 Phase 实现专用查看器
      return (
        <div style={{ marginBottom: 16 }}>
          <Typography.Text type="secondary">{tag} 数据</Typography.Text>
        </div>
      )
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

  // 条件可见性：visibleWhen 不满足时整棵子树不渲染（祖先 return null 即剪枝后代）
  if (!resolveVisibility(attrs, context.visibility)) return null

  // ── Visual 容器/展示标签 ──
  switch (tag) {
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
      return (
        <Typography.Title level={size} style={style} className={attrs.underline ? 'underline' : ''}>
          {attrs.value || text || ''}
        </Typography.Title>
      )
    }
    case 'Markdown': {
      const style = attrs.style ? cssStringToObject(attrs.style) : undefined
      return (
        <div id={attrs.idattr} className={attrs.classname} style={style}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{attrs.value || text || ''}</ReactMarkdown>
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
    case 'Filter':
      return (
        <Input.Search
          placeholder={attrs.placeholder || attrs.value || '搜索...'}
          allowClear
          style={{ marginBottom: 8 }}
        />
      )
    case 'Dialog': {
      const title = attrs.value || text || '对话框'
      return (
        <Card size="small" title={title} style={{ marginBottom: 8 }}>
          {children.map((c) => (
            <ConfigRenderer key={c.name ?? c.tag} node={c} context={context} />
          ))}
        </Card>
      )
    }
    default:
      break
  }

  // ── 对象标签：注册表驱动的预览 ──
  if (node.type === 'object') {
    return renderObjectPreview(node, context)
  }

  // ── 控件/关系标签：注册表驱动分发 ──
  if (node.type === 'control' || node.type === 'relation') {
    const mode = controlMode(tag)
    if (mode === 'unsupported') return <UnsupportedTag tag={tag} />
    if (mode === 'canvas' || mode === 'relation') return null // 画布面板 / RelationPanel 承载
    return renderDomControl(tag, node, context)
  }

  // ── 未知标签：有子节点则递归，否则不渲染 ──
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
