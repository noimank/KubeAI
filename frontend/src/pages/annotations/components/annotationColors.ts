export const LABEL_COLORS = [
  '#1677FF',
  '#52C41A',
  '#FAAD14',
  '#FF4D4F',
  '#722ED1',
  '#13C2C2',
  '#EB2F96',
]

export function labelColor(index: number): string {
  return LABEL_COLORS[index % LABEL_COLORS.length]
}
