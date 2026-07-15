import type { AnnotationResultItem } from '@/types/annotation'
import type { LabelStudioControlConfig } from './parseLabelConfig'

export interface ValidationIssue {
  controlName: string
  message: string
  severity: 'warning' | 'error'
}

/**
 * Validate annotation results against control configs.
 *
 * Currently validates:
 * - `required`: control must produce at least one result
 *
 * @param controls - All control configs from the parsed XML
 * @param results - Serialized annotation results
 * @returns Array of validation issues (empty if all valid)
 */
export function validateAnnotationResults(
  controls: LabelStudioControlConfig[],
  results: AnnotationResultItem[],
): ValidationIssue[] {
  const issues: ValidationIssue[] = []

  for (const ctrl of controls) {
    if (!ctrl.required) continue

    const hasResult = results.some((r) => r.from_name === ctrl.name || r.type === ctrl.type)
    if (!hasResult) {
      issues.push({
        controlName: ctrl.name,
        message: `"${ctrl.name || ctrl.tag}" 为必填项，请完成标注后再提交`,
        severity: 'warning',
      })
    }
  }

  return issues
}
