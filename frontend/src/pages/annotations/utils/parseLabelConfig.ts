/**
 * Label Studio XML 配置解析器 — 树形模型
 *
 * XML 是声明式 UI 树，解析结果保留完整层级结构。
 * workspace 从树中提取空间控件做 canvas 分发，其余节点交给 ConfigRenderer 递归渲染。
 */

// ── Types ──────────────────────────────────────────────────────────────────────

export type ConfigNodeType = 'object' | 'control' | 'visual' | 'relation'

export interface ConfigNode {
  /** XML 标签名 (e.g. "RectangleLabels", "View", "Header") */
  tag: string
  /** 节点分类 */
  type: ConfigNodeType
  /** name 属性值，无则为 null */
  name: string | null
  /** 子节点 */
  children: ConfigNode[]
  /** 所有属性 (key 为 camelCase) */
  attrs: Record<string, string>
  /** 文本内容 (Header/Style/Markdown 等有文本子节点的标签) */
  text: string | null

  // ── 解析期预填便捷字段 ──
  /** 控件标准化类型 (choices / rectanglelabels / textarea / ...) */
  controlType?: string
  /** object 标签的 $fieldname 解析结果 */
  field?: string
  /** Choice/Label 子元素列表 */
  choices?: { value: string; background?: string }[]
  /** Taxonomy 嵌套树 */
  taxonomy?: TaxonomyNode[]
  /** TimeSeries 的 <Channel> 子元素 */
  channels?: TimeSeriesChannel[]
  /** TextArea 的 <Shortcut> 子元素 */
  shortcuts?: ShortcutConfig[]
}

export interface TimeSeriesChannel {
  column: string
  units?: string
  strokeColor?: string
  legend?: string
}

/** TextArea 的 <Shortcut> 子元素：点击/快捷键把 value 注入光标位置 */
export interface ShortcutConfig {
  value: string
  alias?: string
  hotkey?: string
  background?: string
}

export interface TaxonomyNode {
  value: string
  children: TaxonomyNode[]
}

// ── Stable prop types for annotator components (derived from ConfigNode) ────────

export interface LabelStudioObjectConfig {
  tag: string
  name: string
  field: string
}

export interface LabelStudioControlConfig {
  tag: string
  name: string
  toName: string
  type: string
  choice?: string
  choices: { value: string; background?: string }[]
  taxonomy?: TaxonomyNode[]
  perRegion?: boolean
  whenLabelValue?: string | null
  displayMode?: string | null
  required?: boolean
  requiredwhen?: string
  visibleWhen?: string
  defaultValue?: string
  maxUsages?: number
  /** DateTime format string */
  format?: string
  /** TextArea 的 <Shortcut> 子元素 */
  shortcuts?: ShortcutConfig[]
  /** Raw attrs preserved for control-specific attributes (e.g. DateTime 'only') */
  attrs?: Record<string, string>
}

export interface LabelStudioRelationConfig {
  tag: string
  name: string
  toName: string
  type: 'relation' | 'relationlabels'
  choices: { value: string; background?: string }[]
  perRegion?: boolean
}

/** Extract LabelStudioControlConfig from a ConfigNode */
export function toControlConfig(node: ConfigNode): LabelStudioControlConfig {
  const a = node.attrs
  return {
    tag: node.tag,
    name: node.name ?? '',
    toName: a.toname ?? '',
    type: node.controlType ?? '',
    choices: node.choices ?? [],
    choice: a.choice,
    taxonomy: node.taxonomy,
    perRegion: a.perregion === 'true',
    whenLabelValue: a.whenlabelvalue ?? null,
    displayMode: a.displaymode ?? null,
    required: a.required === 'true' || undefined,
    requiredwhen: a.requiredwhen,
    visibleWhen: a.visiblewhen,
    defaultValue: a.defaultvalue,
    maxUsages: a.maxusages ? Number(a.maxusages) : undefined,
    format: a.format,
    shortcuts: node.shortcuts,
    attrs: a,
  }
}

/** Extract LabelStudioObjectConfig from a ConfigNode */
export function toObjectConfig(node: ConfigNode): LabelStudioObjectConfig {
  return {
    tag: node.tag,
    name: node.name ?? '',
    field: node.field ?? '',
  }
}

/** Extract LabelStudioRelationConfig from a ConfigNode */
export function toRelationConfig(node: ConfigNode): LabelStudioRelationConfig {
  return {
    tag: node.tag,
    name: node.name ?? '',
    toName: node.attrs.toname ?? '',
    type: node.controlType as 'relation' | 'relationlabels',
    choices: node.choices ?? [],
    perRegion: node.attrs.perregion === 'true',
  }
}

// ── 标签分类常量 ──────────────────────────────────────────────────────────────

export const OBJECT_TAGS = new Set([
  'Image',
  'Text',
  'Audio',
  'Video',
  'HyperText',
  'PDF',
  'Pdf',
  'Paragraphs',
  'TimeSeries',
  'Table',
  'List',
  'PagedView',
  'Chat',
])

export const CONTROL_TAG_MAP: Record<string, string> = {
  Choices: 'choices',
  RectangleLabels: 'rectanglelabels',
  Rectangle: 'rectangle',
  PolygonLabels: 'polygonlabels',
  Polygon: 'polygon',
  BrushLabels: 'brushlabels',
  Brush: 'brush',
  KeyPointLabels: 'keypointlabels',
  KeyPoint: 'keypoint',
  EllipseLabels: 'ellipselabels',
  Ellipse: 'ellipse',
  Labels: 'labels',
  TextArea: 'textarea',
  Rating: 'rating',
  Number: 'number',
  Taxonomy: 'taxonomy',
  DateTime: 'datetime',
  HyperTextLabels: 'hypertextlabels',
  ParagraphLabels: 'paragraphlabels',
  TimeSeriesLabels: 'timeserieslabels',
  VideoRectangle: 'videorectangle',
  TimelineLabels: 'timelinelabels',
  Pairwise: 'pairwise',
  Ranker: 'ranker',
  MagicWand: 'magicwand',
  VectorLabels: 'vectorlabels',
  Vector: 'vector',
  BitmaskLabels: 'bitmasklabels',
  Bitmask: 'bitmask',
  Relation: 'relation',
  RelationLabels: 'relationlabels',
  Relations: 'relations',
}

// VISUAL_TAGS 常量仅文档用途（当前解析器按 tag 名 classify，不需要此集合）
// const VISUAL_TAGS = new Set(['View', 'Header', 'Style', 'Collapse', 'Panel', 'Markdown'])

const RELATION_TAGS = new Set(['Relation', 'RelationLabels'])

/** 空间控件类型 (创建几何区域) */
export const SPATIAL_CONTROL_TYPES = [
  'rectangle',
  'rectanglelabels',
  'polygon',
  'polygonlabels',
  'keypoint',
  'keypointlabels',
  'ellipse',
  'ellipselabels',
  'brush',
  'brushlabels',
  'labels',
  'hypertextlabels',
  'paragraphlabels',
  'timeserieslabels',
  'videorectangle',
  'timelinelabels',
  'magicwand',
  'vector',
  'vectorlabels',
  'bitmask',
  'bitmasklabels',
]

/** 分类控件类型 (提供标签/文本，支持 perRegion) */
export const CLASSIFICATION_CONTROL_TYPES = [
  'choices',
  'textarea',
  'rating',
  'number',
  'taxonomy',
  'datetime',
]

/** 无内嵌标签的空间控件 */
export const BARE_SPATIAL_CONTROL_TYPES = [
  'rectangle',
  'polygon',
  'keypoint',
  'ellipse',
  'brush',
  'magicwand',
  'vector',
  'bitmask',
]

// ── Helpers ────────────────────────────────────────────────────────────────────

function fieldFromValue(value: string | null): string | null {
  const match = value?.trim().match(/^\$([A-Za-z_][\w.-]*)$/)
  return match?.[1] ?? null
}

function parseChoiceAttributes(node: Element): { value: string; background?: string } | null {
  const value = node.getAttribute('value') || ''
  if (!value) return null
  const bg = node.getAttribute('background') || undefined
  return bg ? { value, background: bg } : { value }
}

function classifyTag(tag: string): ConfigNodeType {
  if (tag === 'Style') return 'visual'
  if (OBJECT_TAGS.has(tag)) return 'object'
  if (RELATION_TAGS.has(tag)) return 'relation'
  if (tag in CONTROL_TAG_MAP) return 'control'
  return 'visual'
}

function buildTaxonomy(element: Element): TaxonomyNode[] {
  const result: TaxonomyNode[] = []
  element.querySelectorAll(':scope > Choice').forEach((child) => {
    const value = child.getAttribute('value') || ''
    if (!value) return
    result.push({ value, children: buildTaxonomy(child) })
  })
  return result
}

function cssStringToObject(style: string): Record<string, string> {
  const result: Record<string, string> = {}
  for (const part of style.split(';')) {
    const colon = part.indexOf(':')
    if (colon === -1) continue
    const key = part.substring(0, colon).trim()
    const value = part.substring(colon + 1).trim()
    if (key) result[key.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value
  }
  return result
}

// ── Parse ──────────────────────────────────────────────────────────────────────

function buildNode(element: Element): ConfigNode {
  const tag = element.tagName
  const type = classifyTag(tag)

  // 构建 attrs — 统一 lowercase key (对齐 LS Tree.tsx attrsToProps)
  const attrs: Record<string, string> = {}
  for (const attr of element.attributes) {
    attrs[attr.name.toLowerCase()] = attr.value
  }

  const name = attrs.name || null
  const field = attrs.value
    ? fieldFromValue(attrs.value)
    : attrs.valuelist
      ? fieldFromValue(attrs.valuelist)
      : null

  // 子元素分类
  const childElements = Array.from(element.children)
  const children = childElements.map(buildNode)

  // 文本内容 (无元素子节点且有文本)
  const rawText = element.textContent?.trim()
  const text = element.children.length === 0 && rawText ? rawText : null

  const node: ConfigNode = { tag, type, name, children, attrs, text }

  // 按节点类型填充便捷字段
  if (type === 'object' && field) {
    node.field = field
  }

  if (type === 'object' && tag === 'TimeSeries') {
    node.channels = childElements
      .filter((c) => c.tagName === 'Channel')
      .map((c) => {
        const ch: TimeSeriesChannel = { column: c.getAttribute('column') || '' }
        const units = c.getAttribute('units')
        const strokeColor = c.getAttribute('strokeColor')
        const legend = c.getAttribute('legend')
        if (units) ch.units = units
        if (strokeColor) ch.strokeColor = strokeColor
        if (legend) ch.legend = legend
        return ch
      })
  }

  if (type === 'control') {
    node.controlType = CONTROL_TAG_MAP[tag]
    node.choices = childElements
      .filter((c) => c.tagName === 'Choice' || c.tagName === 'Label' || c.tagName === 'Relation')
      .map(parseChoiceAttributes)
      .filter((c): c is { value: string; background?: string } => c !== null)
    if (tag === 'Taxonomy') {
      node.taxonomy = buildTaxonomy(element)
    }
    if (tag === 'TextArea') {
      node.shortcuts = childElements
        .filter((c) => c.tagName === 'Shortcut')
        .map((c) => {
          const sc: ShortcutConfig = { value: c.getAttribute('value') || '' }
          const alias = c.getAttribute('alias')
          const hotkey = c.getAttribute('hotkey')
          const background = c.getAttribute('background')
          if (alias) sc.alias = alias
          if (hotkey) sc.hotkey = hotkey
          if (background) sc.background = background
          return sc
        })
        .filter((s) => s.value)
    }
  }

  if (type === 'relation') {
    node.controlType = CONTROL_TAG_MAP[tag]
    node.choices = childElements
      .filter((c) => c.tagName === 'Label')
      .map(parseChoiceAttributes)
      .filter((c): c is { value: string; background?: string } => c !== null)
  }

  return node
}

// ── Public API ─────────────────────────────────────────────────────────────────

export function parseConfigTree(xml: string): ConfigNode {
  const parser = new DOMParser()
  const doc = parser.parseFromString(xml, 'application/xml')
  const errorNode = doc.querySelector('parsererror')
  if (errorNode) {
    throw new Error('标注配置 XML 格式无效')
  }
  return buildNode(doc.documentElement)
}

/** DFS 遍历树，返回所有匹配 predicate 的节点 */
export function findNodes(
  root: ConfigNode,
  predicate: (node: ConfigNode) => boolean,
): ConfigNode[] {
  const result: ConfigNode[] = []
  const walk = (node: ConfigNode) => {
    if (predicate(node)) result.push(node)
    node.children.forEach(walk)
  }
  walk(root)
  return result
}

/** DFS 查找第一个匹配 predicate 的节点 */
export function findFirstNode(
  root: ConfigNode,
  predicate: (node: ConfigNode) => boolean,
): ConfigNode | null {
  if (predicate(root)) return root
  for (const child of root.children) {
    const found = findFirstNode(child, predicate)
    if (found) return found
  }
  return null
}

/** 获取 config 中所有标签值 (用于 AnnotationGuideline) */
export function extractLabels(root: ConfigNode): string[] {
  return findNodes(root, (n) => !!n.choices).flatMap((n) => (n.choices ?? []).map((c) => c.value))
}

// ── Taxonomy 工具 ─────────────────────────────────────────────────────────────

interface AntdTreeNode {
  value: string
  title: string
  children?: AntdTreeNode[]
}

/** 将 TaxonomyNode[] 转为 antd TreeSelect DataNode */
export function taxonomyToTreeData(nodes: TaxonomyNode[] | undefined): AntdTreeNode[] {
  if (!nodes) return []
  return nodes.map((n) => {
    const children = taxonomyToTreeData(n.children)
    return {
      value: n.value,
      title: n.value,
      children: children.length > 0 ? children : undefined,
    }
  })
}

export { cssStringToObject }
