import { ClearOutlined, FileOutlined, FolderOutlined } from '@ant-design/icons'
import { Button, Empty, Space, Tag, Tooltip, Tree, Typography } from 'antd'
import type { DataNode } from 'antd/es/tree'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { browseFilesystem, type FsEntry } from '@/services/filesystem'

const { DirectoryTree } = Tree

export interface FileBrowserProps {
  /** 受控: 已勾选的 canonical 容器路径 (绝对路径), 与 ModelVersionCreate.filePaths 入参一致. */
  value: string[]
  onChange: (paths: string[]) => void
  /** 虚拟根节点列表. 通常 = ``['/kubeai/home', '/kubeai/workspace']``, 后端自动 canoncialize 到当前用户/租户. */
  roots: string[]
  disabled?: boolean
  /** 树容器高度, 默认 360. */
  height?: number
}

function formatBytes(bytes: number | undefined): string {
  if (bytes === undefined || bytes === null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function renderEntryLabel(entry: FsEntry): React.ReactNode {
  return (
    <Space size={6} className="file-browser-entry">
      <Typography.Text style={{ wordBreak: 'break-all' }}>{entry.name}</Typography.Text>
      {entry.type === 'file' && entry.sizeBytes !== undefined ? (
        <Tag color="default" style={{ marginInlineEnd: 0 }}>
          {formatBytes(entry.sizeBytes)}
        </Tag>
      ) : null}
    </Space>
  )
}

function buildNode(entry: FsEntry): DataNode {
  return {
    key: entry.path,
    title: renderEntryLabel(entry),
    isLeaf: entry.type === 'file',
  }
}

function buildRootNode(root: string): DataNode {
  return {
    key: root,
    title: <Typography.Text type="secondary">{root}</Typography.Text>,
    isLeaf: false,
  }
}

function updateChildren(data: DataNode[], targetKey: string, entries: FsEntry[]): DataNode[] {
  return data.map((node) => {
    if (node.key === targetKey) {
      return { ...node, children: entries.map(buildNode) }
    }
    if (node.children) {
      return { ...node, children: updateChildren(node.children as DataNode[], targetKey, entries) }
    }
    return node
  })
}

function flattenChecked(value: unknown): string[] {
  if (Array.isArray(value)) return value as string[]
  if (
    value &&
    typeof value === 'object' &&
    Array.isArray((value as { checked?: string[] }).checked)
  ) {
    return (value as { checked: string[] }).checked
  }
  return []
}

function nodeTitle(node: DataNode): React.ReactNode {
  // antd DataNode.title 类型为 ReactNode | ((data) => ReactNode). 收敛为 ReactNode.
  const t = node.title
  if (t === undefined || t === null) return String(node.key)
  if (typeof t === 'function') {
    return (t as (data: DataNode) => React.ReactNode)(node)
  }
  return t
}

export default function FileBrowser({
  value,
  onChange,
  roots,
  disabled,
  height = 360,
}: FileBrowserProps) {
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [checkedKeys, setCheckedKeys] = useState<string[]>(value)
  const [treeData, setTreeData] = useState<DataNode[]>([])
  // 已加载 entries 缓存 — key = canonical path, value = list of children entries.
  const cacheRef = useRef<Map<string, FsEntry[]>>(new Map())
  const pendingRef = useRef<Set<string>>(new Set())

  // roots 变化时重置 (Modal 重新打开 / 租户切换).
  useEffect(() => {
    setTreeData(roots.map(buildRootNode))
    cacheRef.current.clear()
    setExpandedKeys([])
    setCheckedKeys([])
    onChange([])
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onChange 变化不应触发重置，仅 roots 变更时重置
  }, [roots])

  useEffect(() => {
    setCheckedKeys(value)
  }, [value])

  const ensureLoaded = useCallback(async (key: string): Promise<FsEntry[]> => {
    const cached = cacheRef.current.get(key)
    if (cached) return cached
    if (pendingRef.current.has(key)) {
      // 等到 cache 命中为止 (或超时 5s).
      await new Promise<void>((resolve) => {
        const start = Date.now()
        const timer = setInterval(() => {
          if (cacheRef.current.has(key) || Date.now() - start > 5000) {
            clearInterval(timer)
            resolve()
          }
        }, 30)
      })
      return cacheRef.current.get(key) ?? []
    }
    pendingRef.current.add(key)
    try {
      const resp = await browseFilesystem(key)
      cacheRef.current.set(key, resp.entries)
      return resp.entries
    } finally {
      pendingRef.current.delete(key)
    }
  }, [])

  const loadData = useCallback(
    (node: DataNode) => {
      return ensureLoaded(String(node.key)).then((entries) => {
        setTreeData((prev) => updateChildren(prev, String(node.key), entries))
      })
    },
    [ensureLoaded],
  )

  const handleCheck = useCallback(
    (next: unknown) => {
      const paths = flattenChecked(next)
      setCheckedKeys(paths)
      onChange(paths)
    },
    [onChange],
  )

  const handleClear = useCallback(() => {
    setCheckedKeys([])
    onChange([])
  }, [onChange])

  const toolbar = useMemo(
    () => (
      <div className="file-browser-toolbar">
        <Typography.Text type="secondary">
          已选择 <strong>{checkedKeys.length}</strong> 项
        </Typography.Text>
        <Tooltip title="清空已勾选">
          <Button
            size="small"
            icon={<ClearOutlined />}
            onClick={handleClear}
            disabled={disabled || checkedKeys.length === 0}
          >
            清空
          </Button>
        </Tooltip>
      </div>
    ),
    [checkedKeys.length, disabled, handleClear],
  )

  if (roots.length === 0) {
    return (
      <div className="file-browser" aria-busy={disabled}>
        {toolbar}
        <Empty description="暂无可浏览的目录" />
      </div>
    )
  }

  return (
    <div className="file-browser" aria-busy={disabled}>
      {toolbar}
      <DirectoryTree
        multiple
        checkable={!disabled}
        disabled={disabled}
        treeData={treeData}
        loadData={loadData}
        expandedKeys={expandedKeys}
        onExpand={(keys) => setExpandedKeys(keys as string[])}
        checkedKeys={checkedKeys}
        onCheck={handleCheck as never}
        height={height}
        showLine
        blockNode
        icon={({ isLeaf }) => (isLeaf ? <FileOutlined /> : <FolderOutlined />)}
        titleRender={nodeTitle}
      />
    </div>
  )
}
