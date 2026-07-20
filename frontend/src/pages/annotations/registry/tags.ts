import type { RegionValue } from '../hooks/useAnnotationRegions'

/**
 * 控件标签注册表 —— 单一事实来源，决定每个 control 标签由哪一层面渲染。
 *
 * 消除了过去散落在 parseLabelConfig / ConfigRenderer / workspace 三处的重复标签列表。
 * `registry.test.ts` 断言每个已知控件标签都有条目，从测试期就捕获「标签静默渲染 null」。
 *
 * mode:
 *  - 'canvas'      画布几何控件（创建 Region，由画布面板渲染）
 *  - 'dom'         侧栏 DOM 控件（Choices/TextArea/Rating/... 由 ConfigRenderer 渲染）
 *  - 'relation'    关系控件（由 RelationPanel 渲染，ConfigRenderer 返回 null）
 *  - 'unsupported' 暂未支持的控件（统一渲染 UnsupportedTag 提示，绝不静默 null）
 */
export type ControlMode = 'canvas' | 'dom' | 'relation' | 'unsupported'

export interface ControlEntry {
  mode: ControlMode
  /** canvas 控件创建的 region value kind（仅 mode='canvas' 时有意义） */
  regionKind?: RegionValue['kind']
}

export const controlRegistry: Record<string, ControlEntry> = {
  // ── DOM 分类控件 ──
  Choices: { mode: 'dom' },
  TextArea: { mode: 'dom' },
  Rating: { mode: 'dom' },
  Number: { mode: 'dom' },
  Taxonomy: { mode: 'dom' },
  DateTime: { mode: 'dom' },
  Pairwise: { mode: 'dom' },
  Ranker: { mode: 'dom' },

  // ── 画布几何控件（按 kind 创建 region）──
  RectangleLabels: { mode: 'canvas', regionKind: 'rectangle' },
  Rectangle: { mode: 'canvas', regionKind: 'rectangle' },
  PolygonLabels: { mode: 'canvas', regionKind: 'polygon' },
  Polygon: { mode: 'canvas', regionKind: 'polygon' },
  KeyPointLabels: { mode: 'canvas', regionKind: 'keypoint' },
  KeyPoint: { mode: 'canvas', regionKind: 'keypoint' },
  EllipseLabels: { mode: 'canvas', regionKind: 'ellipse' },
  Ellipse: { mode: 'canvas', regionKind: 'ellipse' },
  BrushLabels: { mode: 'canvas', regionKind: 'brush' },
  Brush: { mode: 'canvas', regionKind: 'brush' },
  Labels: { mode: 'canvas', regionKind: 'textspan' },
  HyperTextLabels: { mode: 'canvas', regionKind: 'textspan' },
  ParagraphLabels: { mode: 'canvas', regionKind: 'paragraphspan' },
  TimeSeriesLabels: { mode: 'canvas', regionKind: 'timeseries' },
  VideoRectangle: { mode: 'canvas', regionKind: 'videorectangle' },
  TimelineLabels: { mode: 'canvas', regionKind: 'timelinelabels' },
  Vector: { mode: 'canvas', regionKind: 'vector' },
  VectorLabels: { mode: 'canvas', regionKind: 'vector' },
  Bitmask: { mode: 'canvas', regionKind: 'bitmask' },
  BitmaskLabels: { mode: 'canvas', regionKind: 'bitmask' },
  MagicWand: { mode: 'canvas', regionKind: 'magicwand' },

  // ── 关系控件（RelationPanel 渲染）──
  Relations: { mode: 'relation' },
  Relation: { mode: 'relation' },
  RelationLabels: { mode: 'relation' },
}

/** 控件渲染模式（未知标签视为 unsupported，确保不会静默 null） */
export function controlMode(tag: string): ControlMode {
  return controlRegistry[tag]?.mode ?? 'unsupported'
}

/** 画布控件的 region kind（非画布控件返回 undefined） */
export function regionKindForControl(tag: string): RegionValue['kind'] | undefined {
  return controlRegistry[tag]?.regionKind
}

// ── Object 标签注册表 ────────────────────────────────────────────────────────

export type ObjectPreview = 'image' | 'audio' | 'video' | 'text' | 'html' | 'none'

export interface ObjectEntry {
  /** 是否作为画布背景（承载 canvas 控件的几何交互） */
  canvas: boolean
  /** DOM 预览种类（侧栏无 canvas 控件时展示） */
  preview: ObjectPreview
}

export const objectRegistry: Record<string, ObjectEntry> = {
  Image: { canvas: true, preview: 'image' },
  Text: { canvas: true, preview: 'text' },
  HyperText: { canvas: true, preview: 'html' },
  Audio: { canvas: true, preview: 'audio' },
  Video: { canvas: true, preview: 'video' },
  Paragraphs: { canvas: true, preview: 'text' },
  Chat: { canvas: true, preview: 'text' },
  TimeSeries: { canvas: true, preview: 'none' },
  Table: { canvas: false, preview: 'none' },
  List: { canvas: false, preview: 'none' },
  PagedView: { canvas: false, preview: 'none' },
  PDF: { canvas: false, preview: 'none' },
  Pdf: { canvas: false, preview: 'none' },
}

/** 对象是否作为画布背景（未知对象标签默认 false） */
export function objectIsCanvas(tag: string): boolean {
  return objectRegistry[tag]?.canvas ?? false
}

/** 对象的 DOM 预览种类（未知对象默认 'none'） */
export function objectPreview(tag: string): ObjectPreview {
  return objectRegistry[tag]?.preview ?? 'none'
}
