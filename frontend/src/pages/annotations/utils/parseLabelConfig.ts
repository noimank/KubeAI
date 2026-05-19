/**
 * Parse labels from LabelStudio XML label config.
 * Extracts <Choice value="...">, <Label value="..."> from <Choices>, <RectangleLabels>, <PolygonLabels>.
 */
export function parseLabelsFromConfig(config: string): string[] {
  const labels: string[] = []
  const valueRegex = /<(?:Choice|Label)\s+value="([^"]+)"/g
  let match: RegExpExecArray | null
  while ((match = valueRegex.exec(config)) !== null) {
    labels.push(match[1])
  }
  return labels
}

export type LabelStudioControlType = 'choices' | 'rectanglelabels' | 'polygonlabels'

export function getControlType(config: string): LabelStudioControlType | null {
  if (/<RectangleLabels\b/.test(config)) return 'rectanglelabels'
  if (/<PolygonLabels\b/.test(config)) return 'polygonlabels'
  if (/<Choices\b/.test(config)) return 'choices'
  return null
}
