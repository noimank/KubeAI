import { describe, it, expect } from 'vitest'
import { deserializeRegions } from '@/pages/annotations/utils/deserializeRegions'
import type { AnnotationResultItem } from '@/types/annotation'

function item(
  type: string,
  value: Record<string, unknown>,
  fromName = 'box',
  toName = 'video',
): AnnotationResultItem {
  return { id: 'r1', from_name: fromName, to_name: toName, type, value } as AnnotationResultItem
}

describe('deserializeRegions', () => {
  it('空输入返回空数组', () => {
    expect(deserializeRegions(null)).toEqual([])
    expect(deserializeRegions(undefined)).toEqual([])
    expect(deserializeRegions([])).toEqual([])
  })

  it('videorectangle 往返（丢弃 time，保留 frame/sequence）', () => {
    const regions = deserializeRegions([
      item('videorectangle', {
        sequence: [
          { frame: 1, enabled: true, x: 10, y: 20, width: 30, height: 40, rotation: 0, time: 0.04 },
        ],
        framesCount: 100,
        duration: 4,
        labels: ['Car'],
      }),
    ])
    expect(regions).toHaveLength(1)
    expect(regions[0].value).toEqual({
      kind: 'videorectangle',
      sequence: [{ frame: 1, enabled: true, x: 10, y: 20, width: 30, height: 40, rotation: 0 }],
    })
    expect(regions[0].label).toBe('Car')
    expect(regions[0].fromName).toBe('box')
  })

  it('timelinelabels 往返', () => {
    const regions = deserializeRegions([
      item(
        'timelinelabels',
        { ranges: [{ start: 5, end: 15 }], timelinelabels: ['Movement'] },
        'tl',
      ),
    ])
    expect(regions[0].value).toEqual({ kind: 'timelinelabels', ranges: [{ start: 5, end: 15 }] })
    expect(regions[0].label).toBe('Movement')
  })

  it('timeserieslabels 往返', () => {
    const regions = deserializeRegions([
      item(
        'timeserieslabels',
        { start: 10, end: 20, instant: false, timeserieslabels: ['Anomaly'] },
        'ts',
        'ts',
      ),
    ])
    expect(regions[0].value).toEqual({ kind: 'timeseries', start: 10, end: 20, instant: false })
  })

  it('labels 带 text → textspan（NER）', () => {
    const regions = deserializeRegions([
      item('labels', { start: 0, end: 5, text: 'hello', labels: ['Greeting'] }, 'lbl', 'text'),
    ])
    expect(regions[0].value).toEqual({ kind: 'textspan', start: 0, end: 5, text: 'hello' })
  })

  it('labels 无 text → audio span', () => {
    const regions = deserializeRegions([
      item('labels', { start: 1.5, end: 2.5, labels: ['Speech'] }, 'lbl', 'audio'),
    ])
    expect(regions[0].value).toEqual({ kind: 'audio', start: 1.5, end: 2.5 })
  })

  it('未知 type 跳过', () => {
    const regions = deserializeRegions([item('rectangle', { x: 10, y: 20, width: 5, height: 5 })])
    expect(regions).toEqual([])
  })
})
