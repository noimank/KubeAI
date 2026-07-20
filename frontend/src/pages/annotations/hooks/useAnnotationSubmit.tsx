import { useCallback } from 'react'
import { Modal } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelAnnotation, submitAnnotation } from '@/services/annotations'
import { getMessageInstance } from '@/utils/messageHolder'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import {
  findNodes,
  toControlConfig,
  toRelationConfig,
  type ConfigNode,
} from '../utils/parseLabelConfig'
import { serializeRegions, type VideoSerializeMeta } from '../utils/serializeRegions'
import { validateAnnotationResults } from '../utils/validation'
import type { useAnnotationRegions } from './useAnnotationRegions'
import type { useAnnotationRelations } from './useAnnotationRelations'
import type { VisibilityState } from '../utils/visibility'

type RegionsHook = ReturnType<typeof useAnnotationRegions>
type RelationsHook = ReturnType<typeof useAnnotationRelations>

interface UseAnnotationSubmitOptions {
  projectId: string | undefined
  currentTask: AnnotationTask | null
  configTree: ConfigNode | null
  spatialControls: ConfigNode[]
  relationControls: ConfigNode[]
  regionsHook: RegionsHook
  relationsHook: RelationsHook
  globalResults: Record<string, AnnotationResultItem[]>
  videoMetaByObject?: Record<string, VideoSerializeMeta>
  goNext: () => Promise<void>
}

export function useAnnotationSubmit(options: UseAnnotationSubmitOptions) {
  const {
    projectId,
    currentTask,
    configTree,
    spatialControls,
    relationControls,
    regionsHook,
    relationsHook,
    globalResults,
    videoMetaByObject,
    goNext,
  } = options
  const queryClient = useQueryClient()

  const submitMutation = useMutation({
    mutationFn: ({ taskId, result }: { taskId: string; result: AnnotationResultItem[] }) =>
      submitAnnotation(taskId, { result }),
    onSuccess: () => {
      getMessageInstance()?.success('标注提交成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', projectId] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTasks'] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTaskSummary'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (tid: string) => cancelAnnotation(tid),
    onSuccess: () => {
      getMessageInstance()?.success('已撤销提交,可以重新标注')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', projectId] })
    },
  })

  const buildSubmitResult = useCallback(
    (): AnnotationResultItem[] =>
      serializeRegions(
        regionsHook.regions,
        spatialControls.map(toControlConfig),
        regionsHook.imageDimensions,
        globalResults,
        relationsHook.relations,
        relationControls.map(toRelationConfig),
        videoMetaByObject,
      ),
    [
      regionsHook.regions,
      regionsHook.imageDimensions,
      globalResults,
      spatialControls,
      relationsHook.relations,
      relationControls,
      videoMetaByObject,
    ],
  )

  const handleSubmit = useCallback(() => {
    if (!currentTask) return
    const result = buildSubmitResult()
    if (result.length === 0) {
      getMessageInstance()?.warning('请先完成标注')
      return
    }
    const allControls = configTree ? findNodes(configTree, (n) => n.controlType !== undefined) : []
    const state: VisibilityState = {
      selectedRegion:
        regionsHook.regions.find((r) => r.id === regionsHook.selectedRegionId) ?? null,
      regions: regionsHook.regions,
      results: result,
    }
    const issues = validateAnnotationResults(allControls.map(toControlConfig), state)
    if (issues.length > 0) {
      Modal.confirm({
        title: '标注未完成',
        content: (
          <ul style={{ paddingLeft: 20, margin: 0 }}>
            {issues.map((issue) => (
              <li key={issue.controlName}>{issue.message}</li>
            ))}
          </ul>
        ),
        okText: '仍然提交',
        cancelText: '继续标注',
        onOk: () => {
          submitMutation.mutate(
            { taskId: currentTask.id, result },
            { onSuccess: async () => await goNext() },
          )
        },
      })
      return
    }
    submitMutation.mutate(
      { taskId: currentTask.id, result },
      { onSuccess: async () => await goNext() },
    )
  }, [
    currentTask,
    buildSubmitResult,
    submitMutation,
    goNext,
    configTree,
    regionsHook.regions,
    regionsHook.selectedRegionId,
  ])

  return { submitMutation, cancelMutation, handleSubmit, buildSubmitResult }
}
