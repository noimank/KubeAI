import type { AnnotationResultItem } from '@/types/annotation'
import type { Region } from '../hooks/useAnnotationRegions'

/**
 * 条件可见性 / 条件必填的求值状态。由 workspace 组装后下发给 ConfigRenderer
 * 与 validation 共用，保证两处对同一条件语法解释一致。
 */
export interface VisibilityState {
  selectedRegion: Region | null
  regions: Region[]
  /** 扁平化的全部结果（全局 + perRegion），供跨控件条件（choice-selected）查询 */
  results: AnnotationResultItem[]
  /** 选中区域的角色（如 Chat 消息的 author role）；由调用方从 region 提取 */
  selectedRegionRole?: string
}

/** 从结果集中取某 Choices 控件当前选中的值列表 */
function chosenValues(results: AnnotationResultItem[], controlName: string): string[] {
  const r = results.find((x) => x.from_name === controlName)
  return (r?.value?.choices as string[] | undefined) ?? []
}

/**
 * 评估 LabelStudio 条件属性。
 *
 * 返回三态：
 *  - `null`：不存在任何条件属性（visiblewhen/whenXxx 均无）——「不适用」
 *  - `true`/`false`：条件已求值
 *
 * 覆盖语法（attrs 键统一小写）：
 *  - visiblewhen="no-region-selected" / requiredwhen 同理
 *  - visiblewhen="region-selected" [+ whenLabelValue / whenRole]
 *  - visiblewhen="choice-selected" [+ whenTagName + whenChoiceValue]
 *  - visiblewhen="label-selected" [+ whenLabelValue]
 *  - whenRole / whenRoleName（选中区域角色匹配，RLHF 用）
 *
 * `whenKey` 区分两种语义：'visiblewhen' 控制渲染，'requiredwhen' 控制必填；
 * 两者语法相同，仅取的属性键不同。未知条件语法返回 true（不在解析缺口上误隐藏）。
 *
 * 调用方对 `null` 的解释不同：可见性把 null 视为「可见」，必填把 null 视为「不强制」。
 */
export function evaluateCondition(
  attrs: Record<string, string>,
  whenKey: 'visiblewhen' | 'requiredwhen',
  state: VisibilityState,
): boolean | null {
  const condition = attrs[whenKey]
  const role = attrs.whenrole || attrs.whenrolename
  const hasCond =
    condition || attrs.whenchoicevalue || attrs.whenlabelvalue || attrs.whenregionselected || role
  if (!hasCond) return null

  if (condition === 'no-region-selected') {
    return state.selectedRegion === null
  }

  if (condition === 'region-selected' || attrs.whenregionselected) {
    if (!state.selectedRegion) return false
    if (attrs.whenlabelvalue && state.selectedRegion.label !== attrs.whenlabelvalue) return false
    if (role && state.selectedRegionRole !== role) return false
    return true
  }

  if (condition === 'choice-selected' || attrs.whenchoicevalue) {
    if (!attrs.whentagname) return true
    const chosen = chosenValues(state.results, attrs.whentagname)
    return !attrs.whenchoicevalue || chosen.includes(attrs.whenchoicevalue)
  }

  if (condition === 'label-selected' || attrs.whenlabelvalue) {
    return state.regions.some((r) => r.label === attrs.whenlabelvalue)
  }

  return true
}

/** 节点是否可见（visiblewhen 求值；无条件 → 可见） */
export function resolveVisibility(attrs: Record<string, string>, state: VisibilityState): boolean {
  return evaluateCondition(attrs, 'visiblewhen', state) !== false
}
