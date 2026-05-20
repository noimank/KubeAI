export type LabelStudioObjectType = 'Image' | 'Text' | 'Audio' | 'Video' | 'HyperText' | 'PDF'

export type LabelStudioControlType =
  | 'choices'
  | 'rectanglelabels'
  | 'polygonlabels'
  | 'brushlabels'
  | 'keypointlabels'
  | 'labels'
  | 'textarea'
  | 'rating'
  | 'number'
  | 'taxonomy'

export interface LabelStudioObjectConfig {
  tag: LabelStudioObjectType
  name: string
  field: string
}

export interface LabelStudioChoiceConfig {
  value: string
  background?: string
}

export interface LabelStudioControlConfig {
  tag: string
  name: string
  toName: string
  type: LabelStudioControlType
  choice?: string
  choices: LabelStudioChoiceConfig[]
}

export interface ParsedLabelConfig {
  objects: LabelStudioObjectConfig[]
  controls: LabelStudioControlConfig[]
  labels: string[]
  error?: string
}

const objectTags = ['Image', 'Text', 'Audio', 'Video', 'HyperText', 'PDF'] as const

const controlTypeByTag: Record<string, LabelStudioControlType> = {
  Choices: 'choices',
  RectangleLabels: 'rectanglelabels',
  PolygonLabels: 'polygonlabels',
  BrushLabels: 'brushlabels',
  KeyPointLabels: 'keypointlabels',
  Labels: 'labels',
  TextArea: 'textarea',
  Rating: 'rating',
  Number: 'number',
  Taxonomy: 'taxonomy',
}

function fieldFromValue(value: string | null): string | null {
  const match = value?.trim().match(/^\$([A-Za-z_][\w.-]*)$/)
  return match?.[1] ?? null
}

export function parseLabelConfig(config: string): ParsedLabelConfig {
  const parser = new DOMParser()
  const xml = parser.parseFromString(config, 'application/xml')
  const errorNode = xml.querySelector('parsererror')
  if (errorNode) return { objects: [], controls: [], labels: [], error: '标注配置 XML 格式无效' }

  const objects: LabelStudioObjectConfig[] = []
  for (const tag of objectTags) {
    xml.querySelectorAll(tag).forEach((node) => {
      const name = node.getAttribute('name')
      const field = fieldFromValue(node.getAttribute('value'))
      if (name && field) objects.push({ tag, name, field })
    })
  }

  const controls: LabelStudioControlConfig[] = []
  for (const [tag, type] of Object.entries(controlTypeByTag)) {
    xml.querySelectorAll(tag).forEach((node) => {
      const name = node.getAttribute('name')
      const toName = node.getAttribute('toName')
      if (!name || !toName) return
      const choices = Array.from(node.querySelectorAll('Choice, Label'))
        .map((child) => ({
          value: child.getAttribute('value') || '',
          background: child.getAttribute('background') || undefined,
        }))
        .filter((choice) => choice.value)
      controls.push({
        tag,
        name,
        toName,
        type,
        choice: node.getAttribute('choice') || undefined,
        choices,
      })
    })
  }

  const labels = controls.flatMap((control) => control.choices.map((choice) => choice.value))
  if (objects.length === 0) return { objects, controls, labels, error: '配置缺少数据标签' }
  if (controls.length === 0) return { objects, controls, labels, error: '配置缺少标注控件' }

  return { objects, controls, labels }
}

export function parseLabelsFromConfig(config: string): string[] {
  return parseLabelConfig(config).labels
}
