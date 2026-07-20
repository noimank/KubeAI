import { describe, it, expect } from 'vitest'
import { validateAnnotationResults } from '@/pages/annotations/utils/validation'
import type { LabelStudioControlConfig } from '@/pages/annotations/utils/parseLabelConfig'
import type { Region } from '@/pages/annotations/hooks/useAnnotationRegions'
import type { AnnotationResultItem } from '@/types/annotation'
import type { VisibilityState } from '@/pages/annotations/utils/visibility'

function ctrl(
  over: Partial<LabelStudioControlConfig> & { name: string; type: string },
): LabelStudioControlConfig {
  return { tag: over.name, toName: 'img', choices: [], attrs: {}, ...over }
}

function rectRegion(
  id: string,
  fromName: string,
  perRegion: Record<string, AnnotationResultItem> = {},
): Region {
  return {
    id,
    fromName,
    value: { kind: 'rectangle', x: 0, y: 0, width: 10, height: 10, rotation: 0 },
    perRegionResults: perRegion,
  }
}

function state(
  results: AnnotationResultItem[],
  regions: Region[] = [],
  extra: Partial<VisibilityState> = {},
): VisibilityState {
  return { selectedRegion: null, regions, results, ...extra }
}

describe('validateAnnotationResults — 严格 from_name 匹配', () => {
  it('两个同类型 Choices 控件不可交叉满足（修复旧 type 回退 bug）', () => {
    const controls = [
      ctrl({ name: 'c1', type: 'choices', required: true }),
      ctrl({ name: 'c2', type: 'choices', required: true }),
    ]
    const results: AnnotationResultItem[] = [
      { from_name: 'c1', to_name: 'img', type: 'choices', value: { choices: ['A'] } },
    ]
    const issues = validateAnnotationResults(controls, state(results))
    // c1 有结果，c2 没有 → 仅 c2 报必填
    expect(issues.filter((i) => i.controlName === 'c1')).toHaveLength(0)
    expect(issues.filter((i) => i.controlName === 'c2' && i.severity === 'error')).toHaveLength(1)
  })
})

describe('validateAnnotationResults — required / requiredWhen', () => {
  it('required 未填写 → error', () => {
    const issues = validateAnnotationResults(
      [ctrl({ name: 'r', type: 'choices', required: true })],
      state([]),
    )
    expect(issues).toHaveLength(1)
    expect(issues[0].severity).toBe('error')
  })
  it('required 已填写 → 无 issue', () => {
    const results: AnnotationResultItem[] = [
      { from_name: 'r', to_name: 'img', type: 'choices', value: { choices: ['A'] } },
    ]
    expect(
      validateAnnotationResults(
        [ctrl({ name: 'r', type: 'choices', required: true })],
        state(results),
      ),
    ).toHaveLength(0)
  })
  it('requiredWhen=region-selected：无选中时不强制；有选中时强制', () => {
    const c = ctrl({ name: 'r', type: 'textarea', attrs: { requiredwhen: 'region-selected' } })
    expect(validateAnnotationResults([c], state([], []))).toHaveLength(0)
    const reg = rectRegion('reg1', 'box')
    const issues = validateAnnotationResults([c], state([], [reg], { selectedRegion: reg }))
    expect(issues.filter((i) => i.severity === 'error')).toHaveLength(1)
  })
})

describe('validateAnnotationResults — 可见性', () => {
  it('visibleWhen=region-selected 且无选中：控件隐藏，required 不触发', () => {
    const c = ctrl({
      name: 'r',
      type: 'choices',
      required: true,
      attrs: { visiblewhen: 'region-selected' },
    })
    expect(validateAnnotationResults([c], state([]))).toHaveLength(0)
  })
  it('visibleWhen=region-selected 且有选中：控件可见，required 正常触发', () => {
    const c = ctrl({
      name: 'r',
      type: 'choices',
      required: true,
      attrs: { visiblewhen: 'region-selected' },
    })
    const reg = rectRegion('reg1', 'box')
    const issues = validateAnnotationResults([c], state([], [reg], { selectedRegion: reg }))
    expect(issues.filter((i) => i.severity === 'error')).toHaveLength(1)
  })
})

describe('validateAnnotationResults — maxChoices', () => {
  it('选择数超过 maxChoices → warning', () => {
    const c = ctrl({ name: 'c', type: 'choices', attrs: { maxchoices: '2' } })
    const results: AnnotationResultItem[] = [
      { from_name: 'c', to_name: 'img', type: 'choices', value: { choices: ['A', 'B', 'C'] } },
    ]
    const issues = validateAnnotationResults([c], state(results))
    expect(issues).toHaveLength(1)
    expect(issues[0].severity).toBe('warning')
  })
})

describe('validateAnnotationResults — Rating 范围', () => {
  it('评分超过 maxstars → warning', () => {
    const c = ctrl({ name: 'rate', type: 'rating', attrs: { maxstars: '5' } })
    const results: AnnotationResultItem[] = [
      { from_name: 'rate', to_name: 'img', type: 'rating', value: { rating: 7 } },
    ]
    expect(validateAnnotationResults([c], state(results))).toHaveLength(1)
  })
  it('评分在范围内 → 无 issue', () => {
    const c = ctrl({ name: 'rate', type: 'rating', attrs: { maxstars: '5' } })
    const results: AnnotationResultItem[] = [
      { from_name: 'rate', to_name: 'img', type: 'rating', value: { rating: 4 } },
    ]
    expect(validateAnnotationResults([c], state(results))).toHaveLength(0)
  })
})

describe('validateAnnotationResults — Number 范围', () => {
  it('数值超出 min/max → warning', () => {
    const c = ctrl({ name: 'n', type: 'number', attrs: { min: '0', max: '100' } })
    const results: AnnotationResultItem[] = [
      { from_name: 'n', to_name: 'img', type: 'number', value: { number: 150 } },
    ]
    expect(validateAnnotationResults([c], state(results))).toHaveLength(1)
  })
})

describe('validateAnnotationResults — perRegion required', () => {
  it('perRegion required：目标对象存在未填写的区域 → warning', () => {
    const box = ctrl({ name: 'box', type: 'rectanglelabels', toName: 'img' })
    const comment = ctrl({
      name: 'comment',
      type: 'textarea',
      toName: 'img',
      perRegion: true,
      required: true,
    })
    const regions = [
      rectRegion('r1', 'box', {
        comment: {
          from_name: 'comment',
          to_name: 'img',
          type: 'textarea',
          value: { text: ['ok'] },
        },
      }),
      rectRegion('r2', 'box'), // 未填写
    ]
    const issues = validateAnnotationResults([box, comment], state([], regions))
    expect(issues.filter((i) => i.controlName === 'comment')).toHaveLength(1)
    expect(issues[0].severity).toBe('warning')
  })
  it('perRegion required：所有区域都已填写 → 无 issue', () => {
    const comment = ctrl({
      name: 'comment',
      type: 'textarea',
      toName: 'img',
      perRegion: true,
      required: true,
    })
    const regions = [
      rectRegion('r1', 'box', {
        comment: {
          from_name: 'comment',
          to_name: 'img',
          type: 'textarea',
          value: { text: ['ok'] },
        },
      }),
    ]
    expect(validateAnnotationResults([comment], state([], regions))).toHaveLength(0)
  })
})
