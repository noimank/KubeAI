import { describe, it, expect } from 'vitest'
import { serializeRegions, serializeRelations } from '@/pages/annotations/utils/serializeRegions'
import type { Region, RegionValue } from '@/pages/annotations/hooks/useAnnotationRegions'
import type { AnnotationRelation } from '@/pages/annotations/hooks/useAnnotationRelations'
import type {
  LabelStudioControlConfig,
  LabelStudioRelationConfig,
} from '@/pages/annotations/utils/parseLabelConfig'
import type { AnnotationResultItem } from '@/types/annotation'

// ── 构造助手 ──────────────────────────────────────────────────────────────────

const DIMS = { width: 100, height: 100 }

/** 构造最小 LabelStudioControlConfig（序列化只用 name/toName/type） */
function ctrl(name: string, type: string, toName = 'img'): LabelStudioControlConfig {
  return { tag: name, name, toName, type, choices: [] }
}

/** 构造一个 Region */
function region(
  id: string,
  fromName: string,
  value: RegionValue,
  label?: string,
  perRegionResults: Record<string, AnnotationResultItem> = {},
): Region {
  return { id, fromName, label, value, perRegionResults }
}

// ── 黄金快照：锁定每种几何的序列化输出（重构前后必须逐字节一致） ────────────

describe('serializeRegions — 几何区域黄金快照', () => {
  it('Rectangle（bare，无 label 键）', () => {
    const r = region('r1', 'box', {
      kind: 'rectangle',
      x: 10,
      y: 20,
      width: 30,
      height: 40,
      rotation: 0,
    })
    const out = serializeRegions([r], [ctrl('box', 'rectangle')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'box',
        to_name: 'img',
        type: 'rectangle',
        value: { x: 10, y: 20, width: 30, height: 40, rotation: 0 },
      },
    ])
  })

  it('RectangleLabels（附 rectanglelabels 键）', () => {
    const r = region(
      'r1',
      'box',
      { kind: 'rectangle', x: 10, y: 20, width: 30, height: 40, rotation: 0 },
      'cat',
    )
    const out = serializeRegions([r], [ctrl('box', 'rectanglelabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'box',
        to_name: 'img',
        type: 'rectanglelabels',
        value: { x: 10, y: 20, width: 30, height: 40, rotation: 0, rectanglelabels: ['cat'] },
      },
    ])
  })

  it('Polygon / PolygonLabels（点为百分比数组）', () => {
    const r = region(
      'r1',
      'poly',
      {
        kind: 'polygon',
        points: [
          [10, 20],
          [30, 40],
        ],
      },
      'road',
    )
    const out = serializeRegions([r], [ctrl('poly', 'polygonlabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'poly',
        to_name: 'img',
        type: 'polygonlabels',
        value: {
          points: [
            [10, 20],
            [30, 40],
          ],
          polygonlabels: ['road'],
        },
      },
    ])
  })

  it('KeyPoint / KeyPointLabels', () => {
    const r = region('r1', 'kp', { kind: 'keypoint', x: 10, y: 20, width: 5 }, 'nose')
    const out = serializeRegions([r], [ctrl('kp', 'keypointlabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'kp',
        to_name: 'img',
        type: 'keypointlabels',
        value: { x: 10, y: 20, width: 5, keypointlabels: ['nose'] },
      },
    ])
  })

  it('Ellipse / EllipseLabels（radiusX=width/2, radiusY=height/2）', () => {
    const r = region(
      'r1',
      'ell',
      { kind: 'ellipse', x: 10, y: 20, width: 30, height: 40, rotation: 0 },
      'face',
    )
    const out = serializeRegions([r], [ctrl('ell', 'ellipselabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'ell',
        to_name: 'img',
        type: 'ellipselabels',
        value: { x: 10, y: 20, radiusX: 15, radiusY: 20, rotation: 0, ellipselabels: ['face'] },
      },
    ])
  })

  it('Brush / BrushLabels（RLE + original_width/height）', () => {
    const r = region(
      'r1',
      'br',
      { kind: 'brush', rle: 'ABC', originalWidth: 50, originalHeight: 60 },
      'masks',
    )
    const out = serializeRegions([r], [ctrl('br', 'brushlabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'br',
        to_name: 'img',
        type: 'brushlabels',
        value: { rle: 'ABC', original_width: 50, original_height: 60, brushlabels: ['masks'] },
      },
    ])
  })

  it('VideoRectangle（sequence 补 time + framesCount + duration + labels）', () => {
    const r = region(
      'r1',
      'box',
      {
        kind: 'videorectangle',
        sequence: [{ frame: 1, enabled: true, x: 10, y: 20, width: 30, height: 40, rotation: 0 }],
      },
      'Car',
    )
    const out = serializeRegions(
      [r],
      [ctrl('box', 'videorectangle', 'video')],
      DIMS,
      {},
      undefined,
      undefined,
      { video: { framerate: 25, framesCount: 100, duration: 4 } },
    )
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'box',
        to_name: 'video',
        type: 'videorectangle',
        value: {
          sequence: [
            {
              frame: 1,
              enabled: true,
              x: 10,
              y: 20,
              width: 30,
              height: 40,
              rotation: 0,
              time: 0.04,
            },
          ],
          framesCount: 100,
          duration: 4,
          labels: ['Car'],
        },
      },
    ])
  })

  it('TimelineLabels（ranges + timelinelabels，无需 videoMeta）', () => {
    const r = region(
      'r1',
      'tl',
      { kind: 'timelinelabels', ranges: [{ start: 5, end: 15 }] },
      'Movement',
    )
    const out = serializeRegions([r], [ctrl('tl', 'timelinelabels', 'video')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'tl',
        to_name: 'video',
        type: 'timelinelabels',
        value: { ranges: [{ start: 5, end: 15 }], timelinelabels: ['Movement'] },
      },
    ])
  })

  it('VectorLabels（vertices 百分比 + closed + vectorlabels）', () => {
    const r = region(
      'r1',
      'vec',
      {
        kind: 'vector',
        vertices: [
          { id: 'p1', x: 10, y: 20, prevPointId: null, isBezier: false },
          { id: 'p2', x: 30, y: 40, prevPointId: 'p1', isBezier: false },
        ],
        closed: true,
      },
      'Road',
    )
    const out = serializeRegions([r], [ctrl('vec', 'vectorlabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'vec',
        to_name: 'img',
        type: 'vectorlabels',
        value: {
          vertices: [
            { id: 'p1', x: 10, y: 20, prevPointId: null, isBezier: false },
            { id: 'p2', x: 30, y: 40, prevPointId: 'p1', isBezier: false },
          ],
          closed: true,
          vectorlabels: ['Road'],
        },
      },
    ])
  })

  it('Vector（bare，无 label 键）', () => {
    const r = region('r1', 'vec', {
      kind: 'vector',
      vertices: [{ id: 'p1', x: 10, y: 20, prevPointId: null, isBezier: false }],
      closed: false,
    })
    const out = serializeRegions([r], [ctrl('vec', 'vector')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'vec',
        to_name: 'img',
        type: 'vector',
        value: {
          vertices: [{ id: 'p1', x: 10, y: 20, prevPointId: null, isBezier: false }],
          closed: false,
        },
      },
    ])
  })

  it('BitmaskLabels（imageDataURL + bitmasklabels）', () => {
    const r = region(
      'r1',
      'mask',
      {
        kind: 'bitmask',
        dataURL: 'data:image/png;base64,abc',
        originalWidth: 100,
        originalHeight: 100,
      },
      'Person',
    )
    const out = serializeRegions([r], [ctrl('mask', 'bitmasklabels')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'mask',
        to_name: 'img',
        type: 'bitmasklabels',
        value: { imageDataURL: 'data:image/png;base64,abc', bitmasklabels: ['Person'] },
      },
    ])
  })

  it('MagicWand（format:rle + rle，无 label 键）', () => {
    const r = region('r1', 'mw', {
      kind: 'magicwand',
      rle: '0 100',
      originalWidth: 100,
      originalHeight: 100,
    })
    const out = serializeRegions([r], [ctrl('mw', 'magicwand')], DIMS, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'mw',
        to_name: 'img',
        type: 'magicwand',
        value: { format: 'rle', rle: '0 100' },
      },
    ])
  })

  it('Labels（文本 span，type 跟随控件，不需 imageDims）', () => {
    const r = region('r1', 'ner', { kind: 'textspan', start: 5, end: 10, text: 'hello' }, 'PER')
    const out = serializeRegions([r], [ctrl('ner', 'labels', 'text')], null, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'ner',
        to_name: 'text',
        type: 'labels',
        value: { start: 5, end: 10, text: 'hello', labels: ['PER'] },
      },
    ])
  })

  it('HyperTextLabels 文本 span 现在正确序列化（重构前被静默丢弃的 bug 修复）', () => {
    const r = region('r1', 'htl', { kind: 'textspan', start: 0, end: 3, text: 'abc' }, 'ORG')
    const out = serializeRegions([r], [ctrl('htl', 'hypertextlabels', 'html')], null, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'htl',
        to_name: 'html',
        type: 'hypertextlabels',
        value: { start: 0, end: 3, text: 'abc', hypertextlabels: ['ORG'] },
      },
    ])
  })

  it('ParagraphLabels（paragraphspan，utterance 内 span）', () => {
    const r = region(
      'r1',
      'slot',
      { kind: 'paragraphspan', paragraphId: '2', start: 4, end: 9, text: 'Seattle' },
      'Location',
    )
    const out = serializeRegions([r], [ctrl('slot', 'paragraphlabels', 'dialogue')], null, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'slot',
        to_name: 'dialogue',
        type: 'paragraphlabels',
        value: { start: 4, end: 9, text: 'Seattle', paragraphlabels: ['Location'] },
      },
    ])
  })

  it('Message 区域不产出几何结果，仅其 perRegion 结果序列化', () => {
    const perRegion: AnnotationResultItem = {
      from_name: 'accuracy',
      to_name: 'chat',
      type: 'rating',
      value: { rating: 5 },
    }
    const r = region(
      'chat:1',
      'chat',
      { kind: 'message', messageId: '1', role: 'assistant' },
      undefined,
      {
        accuracy: perRegion,
      },
    )
    // 'chat' 是对象名而非控件名 → controlMap 无对应 → 无几何结果
    const out = serializeRegions([r], [ctrl('accuracy', 'rating', 'chat')], null, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'chat:1',
        from_name: 'accuracy',
        to_name: 'chat',
        type: 'rating',
        value: { rating: 5 },
      },
    ])
  })

  it('TimeSeriesLabels（timeseries 区间）', () => {
    const r = region(
      'r1',
      'label',
      { kind: 'timeseries', start: 1000, end: 2000, instant: false },
      'Outlier',
    )
    const out = serializeRegions([r], [ctrl('label', 'timeserieslabels', 'ts')], null, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'label',
        to_name: 'ts',
        type: 'timeserieslabels',
        value: { start: 1000, end: 2000, instant: false, timeserieslabels: ['Outlier'] },
      },
    ])
  })

  it('Audio Labels（音频区间，秒）', () => {
    const r = region('r1', 'label', { kind: 'audio', start: 1.5, end: 3.0 }, 'EventA')
    const out = serializeRegions([r], [ctrl('label', 'labels', 'audio')], null, {})
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'r1',
        from_name: 'label',
        to_name: 'audio',
        type: 'labels',
        value: { start: 1.5, end: 3.0, labels: ['EventA'] },
      },
    ])
  })

  it('bare Rectangle 即便有 label 也不输出 label 键', () => {
    const r = region(
      'r1',
      'box',
      { kind: 'rectangle', x: 1, y: 2, width: 3, height: 4, rotation: 0 },
      'ignored',
    )
    const out = serializeRegions([r], [ctrl('box', 'rectangle')], DIMS, {})
    expect(out[0].value).toEqual({ x: 1, y: 2, width: 3, height: 4, rotation: 0 })
  })
})

// ── perRegion + global + relations 组合 ───────────────────────────────────────

describe('serializeRegions — perRegion / global / relations', () => {
  it('perRegion 结果共享区域 id', () => {
    const perRegion: AnnotationResultItem = {
      from_name: 'comment',
      to_name: 'img',
      type: 'textarea',
      value: { text: ['nice'] },
    }
    const r = region(
      'r1',
      'box',
      { kind: 'rectangle', x: 1, y: 2, width: 3, height: 4, rotation: 0 },
      'cat',
      { comment: perRegion },
    )
    const out = serializeRegions(
      [r],
      [ctrl('box', 'rectanglelabels'), ctrl('comment', 'textarea')],
      DIMS,
      {},
    )
    expect(out).toHaveLength(2)
    expect(out[1]).toEqual<AnnotationResultItem>({
      id: 'r1', // 覆盖为区域 id
      from_name: 'comment',
      to_name: 'img',
      type: 'textarea',
      value: { text: ['nice'] },
    })
  })

  it('文本 span region 的 perRegion 也附加', () => {
    const perRegion: AnnotationResultItem = {
      from_name: 'sentiment',
      to_name: 'text',
      type: 'choices',
      value: { choices: ['pos'] },
    }
    const r = region('r1', 'ner', { kind: 'textspan', start: 0, end: 3, text: 'abc' }, 'PER', {
      sentiment: perRegion,
    })
    const out = serializeRegions(
      [r],
      [ctrl('ner', 'labels', 'text'), ctrl('sentiment', 'choices', 'text')],
      null,
      {},
    )
    expect(out).toHaveLength(2)
    expect(out[1].id).toBe('r1')
    expect(out[1].from_name).toBe('sentiment')
  })

  it('全局分类结果原样附加', () => {
    const globalItem: AnnotationResultItem = {
      from_name: 'category',
      to_name: 'img',
      type: 'choices',
      value: { choices: ['A'] },
    }
    const out = serializeRegions([], [], DIMS, { category: [globalItem] })
    expect(out).toEqual([globalItem])
  })

  it('relations 序列化为 from_id/to_id/direction', () => {
    const rel: AnnotationRelation = {
      id: 'rel1',
      fromRegionId: 'r1',
      toRegionId: 'r2',
      direction: 'right',
      label: 'org:founded_by',
      fromName: 'rel',
    }
    const relCtrl: LabelStudioRelationConfig = {
      tag: 'Relations',
      name: 'rel',
      toName: 'text',
      type: 'relation',
      choices: [],
    }
    const out = serializeRelations([rel], [relCtrl])
    expect(out).toEqual<AnnotationResultItem[]>([
      {
        id: 'rel1',
        from_name: 'rel',
        to_name: 'text',
        type: 'relation',
        value: { from_id: 'r1', to_id: 'r2', direction: 'right', labels: ['org:founded_by'] },
      },
    ])
  })

  it('relationlabels 类型用自身类型作为 label 键', () => {
    const rel: AnnotationRelation = {
      id: 'rel1',
      fromRegionId: 'r1',
      toRegionId: 'r2',
      direction: 'left',
      label: 'parent',
      fromName: 'rel',
    }
    const relCtrl: LabelStudioRelationConfig = {
      tag: 'RelationLabels',
      name: 'rel',
      toName: 'text',
      type: 'relationlabels',
      choices: [],
    }
    const out = serializeRelations([rel], [relCtrl])
    expect(out[0].value).toEqual({
      from_id: 'r1',
      to_id: 'r2',
      direction: 'left',
      relationlabels: ['parent'],
    })
  })

  it('无 label 的 relation 不附加 label 键', () => {
    const rel: AnnotationRelation = {
      id: 'rel1',
      fromRegionId: 'r1',
      toRegionId: 'r2',
      direction: 'right',
      fromName: 'rel',
    }
    const relCtrl: LabelStudioRelationConfig = {
      tag: 'Relations',
      name: 'rel',
      toName: 'text',
      type: 'relation',
      choices: [],
    }
    const out = serializeRelations([rel], [relCtrl])
    expect(out[0].value).toEqual({ from_id: 'r1', to_id: 'r2', direction: 'right' })
  })
})

// ── 边界情况 ──────────────────────────────────────────────────────────────────

describe('serializeRegions — 边界', () => {
  it('空间区域在无 imageDims 时跳过几何（不崩溃）', () => {
    const r = region('r1', 'mystery', {
      kind: 'rectangle',
      x: 1,
      y: 2,
      width: 3,
      height: 4,
      rotation: 0,
    })
    const out = serializeRegions([r], [ctrl('mystery', 'rectangle')], null, {})
    expect(out).toEqual([])
  })

  it('空输入返回空数组', () => {
    expect(serializeRegions([], [], null, {})).toEqual([])
  })
})
