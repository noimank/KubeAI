import { describe, it, expect } from 'vitest'
import {
  evaluateCondition,
  resolveVisibility,
  type VisibilityState,
} from '@/pages/annotations/utils/visibility'
import type { Region } from '@/pages/annotations/hooks/useAnnotationRegions'
import type { AnnotationResultItem } from '@/types/annotation'

const NO_SELECTION: VisibilityState = {
  selectedRegion: null,
  regions: [],
  results: [],
}

function region(id: string, label?: string): Region {
  return {
    id,
    fromName: 'box',
    label,
    value: { kind: 'rectangle', x: 0, y: 0, width: 10, height: 10, rotation: 0 },
    perRegionResults: {},
  }
}

function state(partial: Partial<VisibilityState>): VisibilityState {
  return { selectedRegion: null, regions: [], results: [], ...partial }
}

describe('evaluateCondition — 无条件', () => {
  it('无任何条件属性时 evaluateCondition 返回 null（不适用）', () => {
    expect(evaluateCondition({}, 'visiblewhen', NO_SELECTION)).toBeNull()
    expect(evaluateCondition({ name: 'x' }, 'requiredwhen', NO_SELECTION)).toBeNull()
  })
  it('resolveVisibility 在无条件时为可见（null → true）', () => {
    expect(resolveVisibility({}, NO_SELECTION)).toBe(true)
  })
})

describe('evaluateCondition — region-selected', () => {
  it('无选中区域时隐藏', () => {
    expect(resolveVisibility({ visiblewhen: 'region-selected' }, NO_SELECTION)).toBe(false)
  })
  it('有选中区域时显示', () => {
    expect(
      resolveVisibility(
        { visiblewhen: 'region-selected' },
        state({ selectedRegion: region('r1') }),
      ),
    ).toBe(true)
  })
  it('叠加 whenLabelValue：选中区域 label 不匹配时隐藏', () => {
    const s = state({ selectedRegion: region('r1', 'cat') })
    expect(resolveVisibility({ visiblewhen: 'region-selected', whenlabelvalue: 'dog' }, s)).toBe(
      false,
    )
    expect(resolveVisibility({ visiblewhen: 'region-selected', whenlabelvalue: 'cat' }, s)).toBe(
      true,
    )
  })
  it('叠加 whenRole：选中区域角色不匹配时隐藏', () => {
    const s = state({ selectedRegion: region('r1'), selectedRegionRole: 'user' })
    expect(resolveVisibility({ visiblewhen: 'region-selected', whenrole: 'assistant' }, s)).toBe(
      false,
    )
    const s2 = state({ selectedRegion: region('r1'), selectedRegionRole: 'assistant' })
    expect(resolveVisibility({ visiblewhen: 'region-selected', whenrole: 'assistant' }, s2)).toBe(
      true,
    )
  })
})

describe('evaluateCondition — no-region-selected', () => {
  it('无选中时显示，有选中时隐藏（RLHF 提示语）', () => {
    expect(resolveVisibility({ visiblewhen: 'no-region-selected' }, NO_SELECTION)).toBe(true)
    expect(
      resolveVisibility(
        { visiblewhen: 'no-region-selected' },
        state({ selectedRegion: region('r1') }),
      ),
    ).toBe(false)
  })
})

describe('evaluateCondition — choice-selected', () => {
  const resultsWithChoice: AnnotationResultItem[] = [
    { from_name: 'intent', to_name: 'img', type: 'choices', value: { choices: ['buy'] } },
  ]
  it('依赖控件未选择时隐藏', () => {
    expect(
      resolveVisibility(
        { visiblewhen: 'choice-selected', whentagname: 'intent', whenchoicevalue: 'buy' },
        NO_SELECTION,
      ),
    ).toBe(false)
  })
  it('依赖控件选中匹配值时显示', () => {
    expect(
      resolveVisibility(
        { visiblewhen: 'choice-selected', whentagname: 'intent', whenchoicevalue: 'buy' },
        state({ results: resultsWithChoice }),
      ),
    ).toBe(true)
  })
  it('依赖控件选中不匹配值时隐藏', () => {
    expect(
      resolveVisibility(
        { visiblewhen: 'choice-selected', whentagname: 'intent', whenchoicevalue: 'sell' },
        state({ results: resultsWithChoice }),
      ),
    ).toBe(false)
  })
})

describe('evaluateCondition — label-selected', () => {
  it('存在带 whenLabelValue 的区域时显示', () => {
    expect(
      resolveVisibility(
        { visiblewhen: 'label-selected', whenlabelvalue: 'cat' },
        state({ regions: [region('r1', 'cat')] }),
      ),
    ).toBe(true)
    expect(
      resolveVisibility(
        { visiblewhen: 'label-selected', whenlabelvalue: 'dog' },
        state({ regions: [region('r1', 'cat')] }),
      ),
    ).toBe(false)
  })
})

describe('evaluateCondition — requiredwhen 复用同一语法', () => {
  it('requiredwhen=region-selected 在有选中时为必填', () => {
    expect(
      evaluateCondition({ requiredwhen: 'region-selected' }, 'requiredwhen', NO_SELECTION),
    ).toBe(false)
    expect(
      evaluateCondition(
        { requiredwhen: 'region-selected' },
        'requiredwhen',
        state({ selectedRegion: region('r1') }),
      ),
    ).toBe(true)
  })
})

describe('evaluateCondition — 未知语法', () => {
  it('未知 visiblewhen 值默认可见（不在解析缺口上误隐藏）', () => {
    expect(resolveVisibility({ visiblewhen: 'something-new' }, NO_SELECTION)).toBe(true)
  })
})
