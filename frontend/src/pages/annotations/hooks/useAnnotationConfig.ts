import { useMemo } from 'react'
import {
  parseConfigTree,
  findNodes,
  extractLabels,
  type ConfigNode,
} from '../utils/parseLabelConfig'
import { controlMode } from '../registry/tags'

interface ProjectLike {
  labelConfig?: string | null
}

/**
 * 解析标注配置树并派生 workspace 所需的结构化视图：
 *  - configTree      完整配置树（ConfigRenderer 递归渲染）
 *  - spatialControls canvas 控件（画布面板渲染）
 *  - relationControls 关系控件（RelationPanel 渲染）
 *  - objectMap        name → object 节点（分类控件解析引用对象）
 *  - labels           全部标签值（AnnotationGuideline）
 */
export function useAnnotationConfig(project: ProjectLike | undefined) {
  const configTree = useMemo<ConfigNode | null>(() => {
    if (!project?.labelConfig) return null
    try {
      return parseConfigTree(project.labelConfig)
    } catch {
      return null
    }
  }, [project?.labelConfig])

  const spatialControls = useMemo(
    () =>
      configTree
        ? findNodes(configTree, (n) => n.type === 'control' && controlMode(n.tag) === 'canvas')
        : [],
    [configTree],
  )

  const relationControls = useMemo(
    () => (configTree ? findNodes(configTree, (n) => n.type === 'relation') : []),
    [configTree],
  )

  const objectMap = useMemo(() => {
    const map = new Map<string, ConfigNode>()
    if (configTree) {
      for (const n of findNodes(configTree, (n) => n.type === 'object' && !!n.name)) {
        if (n.name) map.set(n.name, n)
      }
    }
    return map
  }, [configTree])

  const labels = useMemo(() => (configTree ? extractLabels(configTree) : []), [configTree])

  return { configTree, spatialControls, relationControls, objectMap, labels }
}
