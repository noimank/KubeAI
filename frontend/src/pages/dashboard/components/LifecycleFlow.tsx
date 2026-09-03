import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  Handle,
  MarkerType,
  Position,
  getViewportForBounds,
  type Edge,
  type Node,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  ApiOutlined,
  AppstoreOutlined,
  BellOutlined,
  CodeOutlined,
  DatabaseOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  MonitorOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SyncOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useRbacStore } from '@/stores/rbacStore'

interface FlowModule {
  name: string
  icon: React.ReactNode
  path: string
  permission: string
}

interface StageDatum {
  num: string
  title: string
  en: string
  desc: string
  color: string
  colorLight: string
  icon: React.ReactNode
  modules: FlowModule[]
}

type FlowStageData = StageDatum & { isFirst: boolean; isLast: boolean } & Record<string, unknown>

const STAGE_DATA: StageDatum[] = [
  {
    num: '01',
    title: '数据准备',
    en: 'DATA',
    desc: '构建高质量数据资产',
    color: '#0ea5e9',
    colorLight: '#38bdf8',
    icon: <DatabaseOutlined />,
    modules: [
      {
        name: '数据集',
        icon: <DatabaseOutlined />,
        path: '/datasets',
        permission: 'datasets:read',
      },
      {
        name: '数据标注',
        icon: <EditOutlined />,
        path: '/annotations',
        permission: 'annotations:read',
      },
      {
        name: '数据探索',
        icon: <SearchOutlined />,
        path: '/data-explore',
        permission: 'data_explore:read',
      },
    ],
  },
  {
    num: '02',
    title: '模型开发',
    en: 'DEVELOP',
    desc: '实验驱动的建模迭代',
    color: '#8b5cf6',
    colorLight: '#a78bfa',
    icon: <ExperimentOutlined />,
    modules: [
      {
        name: '开发环境',
        icon: <CodeOutlined />,
        path: '/dev-environments',
        permission: 'dev_environments:read',
      },
      {
        name: '训练任务',
        icon: <ExperimentOutlined />,
        path: '/training-jobs',
        permission: 'training_jobs:read',
      },
      {
        name: '超参调优',
        icon: <ThunderboltOutlined />,
        path: '/tuning',
        permission: 'tuning:read',
      },
      {
        name: '实验追踪',
        icon: <FileSearchOutlined />,
        path: '/experiments',
        permission: 'experiments:read',
      },
    ],
  },
  {
    num: '03',
    title: '模型上线',
    en: 'SERVE',
    desc: '从模型仓库到在线服务',
    color: '#14b8a6',
    colorLight: '#2dd4bf',
    icon: <SafetyCertificateOutlined />,
    modules: [
      {
        name: '模型仓库',
        icon: <SafetyCertificateOutlined />,
        path: '/models',
        permission: 'models:read',
      },
      { name: '镜像管理', icon: <AppstoreOutlined />, path: '/images', permission: 'images:read' },
      {
        name: '推理服务',
        icon: <ApiOutlined />,
        path: '/inference',
        permission: 'inference_services:read',
      },
    ],
  },
  {
    num: '04',
    title: '运营反馈',
    en: 'OPERATE',
    desc: '监控评估驱动数据回流',
    color: '#f59e0b',
    colorLight: '#fbbf24',
    icon: <MonitorOutlined />,
    modules: [
      {
        name: '监控告警',
        icon: <MonitorOutlined />,
        path: '/monitoring',
        permission: 'monitoring:read',
      },
      {
        name: '通知中心',
        icon: <BellOutlined />,
        path: '/notifications',
        permission: 'notifications:read',
      },
    ],
  },
]

/* 布局常量: 卡片宽高与 index.css 中 .stage-slot/.stage-card 的固定尺寸对应,
   画布为静态展示(禁平移/缩放/拖拽), 视口由这些确定值直接换算 */
const NODE_W = 250
const NODE_H = 318
const NODE_GAP = 80
const LOOP_DROP = 50 // 回流边(含标签)在卡片下方下探的高度
const MIN_ZOOM = 0.2 // 须低于最窄视口下的整幅缩放比, 否则窄屏内容会被裁切且无法拖回
const CONTENT_W = NODE_W * STAGE_DATA.length + NODE_GAP * (STAGE_DATA.length - 1)
const CONTENT_H = NODE_H + LOOP_DROP

function StageNode({ data }: NodeProps<Node<FlowStageData>>) {
  const navigate = useNavigate()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const primary = data.modules.find((m) => hasPermission(m.permission))

  return (
    <div className="stage-slot">
      <span
        className="stage-slab"
        style={{
          background: `linear-gradient(180deg, ${data.color}30, ${data.color}14)`,
          boxShadow: `0 12px 22px -10px ${data.color}59`,
        }}
      />
      <div
        className={`stage-card nodrag${primary ? ' clickable' : ''}`}
        title={primary ? `进入${primary.name}` : undefined}
        onClick={primary ? () => navigate(primary.path) : undefined}
      >
        <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
        <Handle type="source" position={Position.Right} id="out" isConnectable={false} />
        <span
          className="stage-accent"
          style={{ background: `linear-gradient(90deg, ${data.colorLight}, ${data.color})` }}
        />
        <span className="stage-mark" style={{ color: `${data.color}1f` }}>
          {data.num}
        </span>
        <div className="stage-head">
          <span
            className="stage-icon"
            style={{
              background: `linear-gradient(145deg, ${data.colorLight}, ${data.color})`,
              boxShadow: `inset 0 1px 1px rgba(255,255,255,0.55), inset 0 -2px 4px rgba(0,0,0,0.14), 0 8px 16px -6px ${data.color}80`,
            }}
          >
            {data.icon}
          </span>
          <div>
            <div className="stage-name">
              {data.title}
              <span className="stage-en">{data.en}</span>
            </div>
            <div className="stage-desc">{data.desc}</div>
          </div>
        </div>
        <div className="stage-mods">
          {data.modules.map((m) => {
            const ok = hasPermission(m.permission)
            return (
              <button
                key={m.name}
                type="button"
                className={`mod nodrag${ok ? '' : ' locked'}`}
                title={ok ? `进入${m.name}` : '当前角色无访问权限'}
                onClick={
                  ok
                    ? (e) => {
                        e.stopPropagation()
                        navigate(m.path)
                      }
                    : undefined
                }
              >
                <span
                  className="mod-icon"
                  style={{
                    background: `linear-gradient(145deg, ${data.colorLight}, ${data.color})`,
                    boxShadow: `inset 0 1px 1px rgba(255,255,255,0.55), inset 0 -2px 3px rgba(0,0,0,0.14), 0 5px 10px -3px ${data.color}73`,
                  }}
                >
                  {m.icon}
                </span>
                <span className="mod-name">{m.name}</span>
              </button>
            )
          })}
        </div>
        {data.isLast && (
          <Handle type="source" position={Position.Bottom} id="fb-out" isConnectable={false} />
        )}
        {data.isFirst && (
          <Handle type="target" position={Position.Bottom} id="fb-in" isConnectable={false} />
        )}
      </div>
    </div>
  )
}

const nodeTypes = { stage: StageNode }

/**
 * 全流程闭环全景 (React Flow 静态展示):
 * 四阶段卡片正向排布, 内嵌功能模块按钮可点击跳转;
 * animated 边表达主流程与自「运营反馈」回到「数据准备」的回流闭环.
 * 视口按内容宽高确定性换算并随容器尺寸变化重新居中, 平移/缩放/拖拽全量禁用;
 * 无对应权限的模块置灰不可点, 但仍展示 —— 概览页承担平台能力全景的叙事职能.
 */
export default function LifecycleFlow() {
  const canvasRef = useRef<HTMLDivElement>(null)
  const rfRef = useRef<ReactFlowInstance<Node<FlowStageData>> | null>(null)

  /** fitView 只按节点包围盒计算(不含卡片下方的回流边), 故手动换算含回流边在内的
   *  完整内容包围盒 → 视口, 确保视觉上真正水平/垂直居中. */
  const centerViewport = useCallback(() => {
    const canvas = canvasRef.current
    const rf = rfRef.current
    if (!canvas || !rf) return
    const { width, height } = canvas.getBoundingClientRect()
    rf.setViewport(
      getViewportForBounds(
        { x: 0, y: 0, width: CONTENT_W, height: CONTENT_H },
        width,
        height,
        MIN_ZOOM,
        1,
        0.05,
      ),
    )
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(centerViewport)
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [centerViewport])

  const nodes = useMemo<Node<FlowStageData>[]>(
    () =>
      STAGE_DATA.map((d, i) => {
        const data: FlowStageData = { ...d, isFirst: i === 0, isLast: i === STAGE_DATA.length - 1 }
        return {
          id: `stage-${i}`,
          type: 'stage',
          position: { x: i * (NODE_W + NODE_GAP), y: 0 },
          data,
        }
      }),
    [],
  )

  const edges = useMemo<Edge[]>(() => {
    const main: Edge[] = STAGE_DATA.slice(0, -1).map((s, i) => ({
      id: `flow-${i}`,
      source: `stage-${i}`,
      sourceHandle: 'out',
      target: `stage-${i + 1}`,
      targetHandle: 'in',
      type: 'smoothstep',
      animated: true,
      style: { stroke: s.color, strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: s.color, width: 16, height: 16 },
    }))
    const feedback: Edge = {
      id: 'feedback',
      source: `stage-${STAGE_DATA.length - 1}`,
      sourceHandle: 'fb-out',
      target: 'stage-0',
      targetHandle: 'fb-in',
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#f59e0b', strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#f59e0b', width: 16, height: 16 },
      label: '反馈回流 · 监控评估与业务反馈驱动数据迭代',
      labelShowBg: true,
      labelBgPadding: [12, 6],
      labelBgBorderRadius: 999,
      labelBgStyle: { fill: '#fff', stroke: 'rgba(245,158,11,0.55)', strokeWidth: 1 },
      labelStyle: { fill: '#b45309', fontSize: 12.5, fontWeight: 600 },
    }
    return [...main, feedback]
  }, [])

  return (
    <div className="flow-card">
      <div className="flow-head">
        <span className="flow-head-title">
          <SyncOutlined className="flow-head-spin" />
          数据飞轮 · 持续迭代
        </span>
        <span className="flow-legend">
          <span className="flow-legend-item">
            <RightOutlined /> 主流程
          </span>
          <span className="flow-legend-item">
            <span className="flow-legend-dashed" /> 反馈回流
          </span>
        </span>
      </div>
      <div ref={canvasRef} className="rf-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          proOptions={{ hideAttribution: true }}
          onInit={(instance) => {
            rfRef.current = instance
            centerViewport()
          }}
          minZoom={MIN_ZOOM}
          maxZoom={1}
          panOnDrag={false}
          panOnScroll={false}
          selectionOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        />
      </div>
    </div>
  )
}
