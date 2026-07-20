import { describe, it, expect } from 'vitest'
import { OBJECT_TAGS, CONTROL_TAG_MAP } from '@/pages/annotations/utils/parseLabelConfig'
import { controlRegistry, objectRegistry } from '@/pages/annotations/registry/tags'

/**
 * 注册表完备性 —— 捕获「解析器识别标签 X，但注册表无条目」这一整类 bug。
 * 这是本次重构要消灭的核心问题：过去标签会静默渲染 null。
 * 新架构下，未知标签落入 'unsupported'（渲染 UnsupportedTag），而已知标签必须有刻意分类。
 */
describe('registry — 控件标签完备性', () => {
  const controlTags = Object.keys(CONTROL_TAG_MAP)

  it('解析器识别的每个控件标签都在 controlRegistry 中有刻意分类', () => {
    const missing = controlTags.filter((tag) => !(tag in controlRegistry))
    expect(missing, `未分类的控件标签: ${missing.join(', ')}`).toEqual([])
  })

  it('画布控件都声明了 regionKind', () => {
    const canvasWithoutKind = controlTags
      .filter((tag) => controlRegistry[tag]?.mode === 'canvas')
      .filter((tag) => !controlRegistry[tag]?.regionKind)
    expect(canvasWithoutKind, `画布控件缺 regionKind: ${canvasWithoutKind.join(', ')}`).toEqual([])
  })

  it('canvas/dom/relation 三类 mode 都有代表（unsupported 为过渡态，控件全部实现后可为空）', () => {
    const modes = new Set(controlTags.map((tag) => controlRegistry[tag]?.mode))
    for (const m of ['canvas', 'dom', 'relation'] as const) {
      expect(modes.has(m), `mode="${m}" 无任何控件`).toBe(true)
    }
  })
})

describe('registry — 对象标签完备性', () => {
  const objectTags = Array.from(OBJECT_TAGS)

  it('解析器识别的每个对象标签都在 objectRegistry 中有刻意分类', () => {
    const missing = objectTags.filter((tag) => !(tag in objectRegistry))
    expect(missing, `未分类的对象标签: ${missing.join(', ')}`).toEqual([])
  })

  it('canvas 对象与 DOM 预览对象都存在', () => {
    const entries = objectTags.map((tag) => objectRegistry[tag])
    expect(entries.some((e) => e?.canvas)).toBe(true)
    expect(entries.some((e) => !e?.canvas)).toBe(true)
  })
})
