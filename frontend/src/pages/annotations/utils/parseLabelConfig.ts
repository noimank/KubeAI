export type LabelStudioObjectType = 'Image' | 'Text' | 'Audio' | 'Video' | 'HyperText' | 'PDF' | 'Header' | 'Style'

export type LabelStudioControlType =
  | 'choices'
  | 'rectanglelabels'
  | 'rectangle'
  | 'polygonlabels'
  | 'polygon'
  | 'brushlabels'
  | 'brush'
  | 'keypointlabels'
  | 'keypoint'
  | 'ellipselabels'
  | 'ellipse'
  | 'labels'
  | 'textarea'
  | 'rating'
  | 'number'
  | 'taxonomy'
  | 'relation'
  | 'relationlabels'

export interface LabelStudioObjectConfig {
  tag: LabelStudioObjectType
  name: string
  field: string
  /** Header text content */
  value?: string
  /** Style attributes from <Style> tag */
  styles?: Record<string, string>
}

export interface LabelStudioChoiceConfig {
  value: string
  background?: string
}

export interface TaxonomyNode {
  value: string
  children: TaxonomyNode[]
}

export interface LabelStudioControlConfig {
  tag: string
  name: string
  toName: string
  type: LabelStudioControlType
  choice?: string
  choices: LabelStudioChoiceConfig[]
  /** Taxonomy 控件的嵌套 Choice 树 */
  taxonomy?: TaxonomyNode[]
  /** perRegion: 结果绑定到选中的空间区域而非整个 task */
  perRegion?: boolean
  /** 仅当区域标签匹配时可见 */
  whenLabelValue?: string | null
  /** perRegion 展示模式: "tag" | "region-list" */
  displayMode?: string | null
  /** 是否必填 */
  required?: boolean
  /** 条件必填表达式 */
  requiredwhen?: string
  /** 条件可见表达式 */
  visibleWhen?: string
  /** 默认值 */
  defaultValue?: string
  /** 标签最大使用次数 */
  maxUsages?: number
}

export interface LabelStudioRelationConfig {
  tag: string
  name: string
  toName: string
  type: 'relation' | 'relationlabels'
  choices: LabelStudioChoiceConfig[]
  perRegion?: boolean
}

/** 空间控件类型（创建几何区域） */
export const SPATIAL_CONTROL_TYPES: LabelStudioControlType[] = [
  'rectangle', 'rectanglelabels',
  'polygon', 'polygonlabels',
  'keypoint', 'keypointlabels',
  'ellipse', 'ellipselabels',
  'brush', 'brushlabels',
  'labels',
]

/** 分类控件类型（提供标签/文本，支持 perRegion） */
export const CLASSIFICATION_CONTROL_TYPES: LabelStudioControlType[] = [
  'choices', 'textarea', 'rating', 'number', 'taxonomy',
]

/** 无内嵌标签的空间控件（可与独立的 Labels/TextArea 配合） */
export const BARE_SPATIAL_CONTROL_TYPES: LabelStudioControlType[] = [
  'rectangle', 'polygon', 'keypoint', 'ellipse', 'brush',
]

export interface ParsedLabelConfig {
  objects: LabelStudioObjectConfig[]
  controls: LabelStudioControlConfig[]
  relations: LabelStudioRelationConfig[]
  labels: string[]
  error?: string
}

const objectTags = ['Image', 'Text', 'Audio', 'Video', 'HyperText', 'PDF'] as const

const controlTypeByTag: Record<string, LabelStudioControlType> = {
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
  Relation: 'relation',
  RelationLabels: 'relationlabels',
}

function fieldFromValue(value: string | null): string | null {
  const match = value?.trim().match(/^\$([A-Za-z_][\w.-]*)$/)
  return match?.[1] ?? null
}

function parseBooleanAttr(value: string | null): boolean | undefined {
  if (!value) return undefined
  return value.toLowerCase() === 'true' || undefined
}

function parseChoiceAttributes(node: Element): LabelStudioChoiceConfig | null {
  const value = node.getAttribute('value') || ''
  if (!value) return null
  return {
    value,
    background: node.getAttribute('background') || undefined,
  }
}

export function parseLabelConfig(config: string): ParsedLabelConfig {
  const parser = new DOMParser()
  const xml = parser.parseFromString(config, 'application/xml')
  const errorNode = xml.querySelector('parsererror')
  if (errorNode) return { objects: [], controls: [], relations: [], labels: [], error: '标注配置 XML 格式无效' }

  const objects: LabelStudioObjectConfig[] = []

  // Parse data object tags
  for (const tag of objectTags) {
    xml.querySelectorAll(tag).forEach((node) => {
      const name = node.getAttribute('name')
      const field = fieldFromValue(node.getAttribute('value'))
      if (name && field) objects.push({ tag, name, field })
    })
  }

  // Parse Header tags as layout objects
  xml.querySelectorAll('Header').forEach((node) => {
    const name = node.getAttribute('name')
    const headerValue = node.getAttribute('value') || node.textContent?.trim() || ''
    if (name) {
      objects.push({ tag: 'Header', name, field: '', value: headerValue })
    }
  })

  // Parse Style tags as layout objects
  xml.querySelectorAll('Style').forEach((node) => {
    const name = node.getAttribute('name')
    if (name) {
      const styles: Record<string, string> = {}
      for (const attr of node.attributes) {
        if (attr.name !== 'name') styles[attr.name] = attr.value
      }
      objects.push({ tag: 'Style', name, field: '', styles })
    }
  })

  // Parse control tags
  const controls: LabelStudioControlConfig[] = []
  for (const [tag, type] of Object.entries(controlTypeByTag)) {
    // Skip relation types — parsed separately below
    if (tag === 'Relation' || tag === 'RelationLabels') continue

    xml.querySelectorAll(tag).forEach((node) => {
      const name = node.getAttribute('name')
      const toName = node.getAttribute('toName')
      if (!name || !toName) return

      const choices = Array.from(node.querySelectorAll('Choice, Label'))
        .map(parseChoiceAttributes)
        .filter((c): c is LabelStudioChoiceConfig => c !== null)

      controls.push({
        tag,
        name,
        toName,
        type,
        choice: node.getAttribute('choice') || undefined,
        choices,
        taxonomy: type === 'taxonomy' ? buildTaxonomy(node) : undefined,
        perRegion: parseBooleanAttr(node.getAttribute('perRegion')),
        whenLabelValue: node.getAttribute('whenLabelValue') || undefined,
        displayMode: node.getAttribute('displayMode') || undefined,
        required: parseBooleanAttr(node.getAttribute('required')),
        requiredwhen: node.getAttribute('requiredwhen') || undefined,
        visibleWhen: node.getAttribute('visibleWhen') || undefined,
        defaultValue: node.getAttribute('defaultValue') || undefined,
        maxUsages: node.getAttribute('maxUsages')
          ? parseInt(node.getAttribute('maxUsages')!, 10)
          : undefined,
      })
    })
  }

  // Parse Relation / RelationLabels
  const relations: LabelStudioRelationConfig[] = []
  for (const tag of ['Relation', 'RelationLabels']) {
    xml.querySelectorAll(tag).forEach((node) => {
      const name = node.getAttribute('name')
      const toName = node.getAttribute('toName')
      if (!name || !toName) return
      const type = tag === 'RelationLabels' ? 'relationlabels' : 'relation'
      const choices = Array.from(node.querySelectorAll('Label'))
        .map(parseChoiceAttributes)
        .filter((c): c is LabelStudioChoiceConfig => c !== null)

      relations.push({
        tag,
        name,
        toName,
        type: type as 'relation' | 'relationlabels',
        choices,
        perRegion: parseBooleanAttr(node.getAttribute('perRegion')),
      })
    })
  }

  const labels = controls.flatMap((control) => control.choices.map((choice) => choice.value))
  if (objects.length === 0) return { objects, controls, relations, labels, error: '配置缺少数据标签' }
  if (controls.length === 0) return { objects, controls, relations, labels, error: '配置缺少标注控件' }

  return { objects, controls, relations, labels }
}

export function parseLabelsFromConfig(config: string): string[] {
  return parseLabelConfig(config).labels
}

/** 递归构建 Taxonomy Choice 树 */
function buildTaxonomy(node: Element): TaxonomyNode[] {
  const result: TaxonomyNode[] = []
  node.querySelectorAll(':scope > Choice').forEach((child) => {
    const value = child.getAttribute('value') || ''
    if (!value) return
    const children = buildTaxonomy(child)
    result.push({ value, children })
  })
  return result
}

interface TaxonomyTreeNode {
  value: string
  title: string
  children?: TaxonomyTreeNode[]
}

/** 将 TaxonomyNode[] 转为 antd TreeSelect 的 DataNode 树 */
export function taxonomyToTreeData(nodes: TaxonomyNode[] | undefined): TaxonomyTreeNode[] {
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
