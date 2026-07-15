import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// ── Types ───────────────────────────────────────────────────────────────────

export interface AnnotationRelation {
  id: string
  /** Source region (arrow origin) */
  fromRegionId: string
  /** Target region (arrow destination) */
  toRegionId: string
  /** Relation label (from RelationLabels choices) */
  label?: string
  /** Direction: left-to-right or bidirectional */
  direction?: 'left' | 'right' | 'bidirectional'
  /** The control name that created this relation */
  sourceControlName: string
}

export interface UseAnnotationRelationsOptions {
  taskId: string
  readOnly?: boolean
}

export interface UseAnnotationRelationsReturn {
  relations: AnnotationRelation[]
  selectedRelationId: string | null
  selectRelation: (id: string | null) => void
  addRelation: (relation: AnnotationRelation) => void
  removeRelation: (id: string) => void
  getRelationsForRegion: (regionId: string) => AnnotationRelation[]
  restoreRelations: (relations: AnnotationRelation[]) => void
  clearRelations: () => void
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useAnnotationRelations(
  options: UseAnnotationRelationsOptions,
): UseAnnotationRelationsReturn {
  const { taskId, readOnly = false } = options
  const [relations, setRelations] = useState<AnnotationRelation[]>([])
  const [selectedRelationId, setSelectedRelationId] = useState<string | null>(null)
  const taskIdRef = useRef(taskId)

  useEffect(() => {
    if (taskIdRef.current !== taskId) {
      taskIdRef.current = taskId
      setRelations([])
      setSelectedRelationId(null)
    }
  }, [taskId])

  const selectRelation = useCallback((id: string | null) => {
    setSelectedRelationId(id)
  }, [])

  const addRelation = useCallback(
    (relation: AnnotationRelation) => {
      if (readOnly) return
      setRelations((prev) => [...prev, relation])
    },
    [readOnly],
  )

  const removeRelation = useCallback(
    (id: string) => {
      if (readOnly) return
      setRelations((prev) => prev.filter((r) => r.id !== id))
      setSelectedRelationId((prev) => (prev === id ? null : prev))
    },
    [readOnly],
  )

  const getRelationsForRegion = useCallback(
    (regionId: string): AnnotationRelation[] => {
      return relations.filter((r) => r.fromRegionId === regionId || r.toRegionId === regionId)
    },
    [relations],
  )

  const restoreRelations = useCallback((restored: AnnotationRelation[]) => {
    setRelations(restored)
    setSelectedRelationId(null)
  }, [])

  const clearRelations = useCallback(() => {
    setRelations([])
    setSelectedRelationId(null)
  }, [])

  return useMemo(
    () => ({
      relations,
      selectedRelationId,
      selectRelation,
      addRelation,
      removeRelation,
      getRelationsForRegion,
      restoreRelations,
      clearRelations,
    }),
    [
      relations,
      selectedRelationId,
      selectRelation,
      addRelation,
      removeRelation,
      getRelationsForRegion,
      restoreRelations,
      clearRelations,
    ],
  )
}
