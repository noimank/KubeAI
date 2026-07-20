import type { LabelStudioControlConfig } from './parseLabelConfig'
import { evaluateCondition, resolveVisibility, type VisibilityState } from './visibility'

export interface ValidationIssue {
  controlName: string
  message: string
  severity: 'warning' | 'error'
}

/**
 * 按控件配置校验标注结果。
 *
 * 规则：
 *  - 严格按 from_name 匹配（删除旧的 type 回退，避免跨同类型控件误判）
 *  - 不可见控件（visibleWhen）整体跳过
 *  - required / requiredWhen 缺失 → error
 *  - Choices maxChoices 超限 → warning
 *  - Rating 超出 [1, maxRating] → warning（maxRating 读 maxstars，默认 10）
 *  - Number 超出 [min, max] → warning
 *  - perRegion + required：目标对象的每个区域都需填写 → 缺失 warning
 */
export function validateAnnotationResults(
  controls: LabelStudioControlConfig[],
  state: VisibilityState,
): ValidationIssue[] {
  const issues: ValidationIssue[] = []
  const { results, regions } = state
  // 控件 name → toName，用于 perRegion 校验定位目标对象的区域
  const controlToName = new Map(controls.map((c) => [c.name, c.toName]))

  for (const ctrl of controls) {
    const attrs = ctrl.attrs ?? {}

    // 不可见控件跳过（不参与必填等任何校验）
    if (!resolveVisibility(attrs, state)) continue

    const matched = results.filter((r) => r.from_name === ctrl.name)
    const reqWhen = evaluateCondition(attrs, 'requiredwhen', state)
    const isRequired = ctrl.required === true || reqWhen === true

    // perRegion 控件不产生全局结果，必填语义改为「目标对象的每个区域都已填写」
    if (ctrl.perRegion) {
      if (isRequired) {
        const targetRegions = regions.filter((r) => controlToName.get(r.fromName) === ctrl.toName)
        const missing = targetRegions.filter((r) => !r.perRegionResults[ctrl.name])
        if (missing.length > 0) {
          issues.push({
            controlName: ctrl.name,
            message: `"${ctrl.name}" 需为每个区域填写（还有 ${missing.length} 个区域未完成）`,
            severity: 'warning',
          })
        }
      }
      continue
    }

    const hasResult = matched.length > 0
    if (isRequired && !hasResult) {
      issues.push({
        controlName: ctrl.name,
        message: `"${ctrl.name || ctrl.tag}" 为必填项，请完成标注后再提交`,
        severity: 'error',
      })
      continue // 必填未满足时，下面的内容校验无意义
    }

    if (!hasResult) continue

    // Choices maxChoices
    if (ctrl.type === 'choices' && attrs.maxchoices) {
      const max = Number(attrs.maxchoices)
      for (const r of matched) {
        const choices = (r.value.choices as string[] | undefined) ?? []
        if (choices.length > max) {
          issues.push({
            controlName: ctrl.name,
            message: `"${ctrl.name}" 最多选择 ${max} 项`,
            severity: 'warning',
          })
        }
      }
    }

    // Rating 范围
    if (ctrl.type === 'rating') {
      const max = attrs.maxstars ? Number(attrs.maxstars) : 10
      for (const r of matched) {
        const rating = r.value.rating
        if (typeof rating === 'number' && (rating < 1 || rating > max)) {
          issues.push({
            controlName: ctrl.name,
            message: `评分必须在 1-${max} 之间`,
            severity: 'warning',
          })
        }
      }
    }

    // Number 范围
    if (ctrl.type === 'number') {
      const min = attrs.min ? Number(attrs.min) : undefined
      const max = attrs.max ? Number(attrs.max) : undefined
      for (const r of matched) {
        const n = r.value.number
        if (typeof n !== 'number') continue
        if (min !== undefined && n < min) {
          issues.push({
            controlName: ctrl.name,
            message: `数值不能小于 ${min}`,
            severity: 'warning',
          })
        }
        if (max !== undefined && n > max) {
          issues.push({
            controlName: ctrl.name,
            message: `数值不能大于 ${max}`,
            severity: 'warning',
          })
        }
      }
    }
  }

  return issues
}
