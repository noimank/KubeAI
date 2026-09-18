import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Button,
  Modal,
  Select,
  Table,
  Input,
  InputNumber,
  Popconfirm,
  Space,
  Spin,
  Tooltip,
  Typography,
  Tag,
} from 'antd'
import {
  PlayCircleOutlined,
  DownloadOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  StopOutlined,
  TableOutlined,
  FileTextOutlined,
  SearchOutlined,
  FolderOutlined,
} from '@ant-design/icons'
import VirtualList from 'rc-virtual-list'
import dayjs from 'dayjs'

import ConnectionFormModal from './ConnectionFormModal'
import SaveToFileModal from './SaveToFileModal'
import SqlEditor from './SqlEditor'
import {
  getDbConnections,
  deleteDbConnection,
  executeQuery,
  listTables,
  getTableSchema,
  saveQueryResult,
} from '@/services/dataExplore'
import type {
  DbConnection,
  DbConnectionCreate,
  DbConnectionUpdate,
  ColumnInfo,
  QueryResult,
  TableInfo,
} from '@/types/dataExplore'
import { DB_TYPE_LABELS } from '@/types/dataExplore'
import type { DbType } from '@/types/dataExplore'
import { getMessageInstance } from '@/utils/messageHolder'

// 与后端 QueryExecutor.TABLE_LIST_LIMIT 一致：达到该数量说明表列表可能被截断
const TABLE_LIST_LIMIT = 20000
// 侧栏虚拟列表统一行高（分组头与表项）
const SIDEBAR_ROW_HEIGHT = 34

type SidebarRow =
  | { kind: 'header'; key: string; schema: string; count: number }
  | { kind: 'table'; key: string; schema: string; table: TableInfo; active: boolean }

export default function DataExplorePage() {
  // 连接
  const [connections, setConnections] = useState<DbConnection[]>([])
  const [selectedConnId, setSelectedConnId] = useState<string | null>(null)
  const [connectionsLoading, setConnectionsLoading] = useState(false)

  // 连接 Modal
  const [connModalOpen, setConnModalOpen] = useState(false)
  const [editingConnection, setEditingConnection] = useState<DbConnection | null>(null)

  // Table list
  const [tables, setTables] = useState<TableInfo[]>([])
  const [tablesLoading, setTablesLoading] = useState(false)
  const [searchTableText, setSearchTableText] = useState('')
  const [activeTableName, setActiveTableName] = useState<string | null>(null)

  // Schema 弹窗
  const [schemaModalOpen, setSchemaModalOpen] = useState(false)
  const [schemaTableName, setSchemaTableName] = useState('')
  const [schemaColumns, setSchemaColumns] = useState<ColumnInfo[]>([])
  const [schemaDetailLoading, setSchemaDetailLoading] = useState(false)

  // SQL 编辑
  const [sql, setSql] = useState('SELECT 1')
  const [maxRows, setMaxRows] = useState(1000)
  const [timeout, setTimeout_] = useState(30)

  // 查询
  const [queryLoading, setQueryLoading] = useState(false)
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null)

  // 保存 Modal
  const [saveModalOpen, setSaveModalOpen] = useState(false)

  // 结果区域高度测量（用于 Table scroll.y 粘性表头）
  const resultsContainerRef = useRef<HTMLDivElement>(null)
  const [resultsHeight, setResultsHeight] = useState(300)

  // 侧栏高度测量（用于表列表虚拟滚动）
  const sidebarListRef = useRef<HTMLDivElement>(null)
  const [sidebarHeight, setSidebarHeight] = useState(400)

  useEffect(() => {
    const el = resultsContainerRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      // 预留底部状态栏高度 ~32px
      setResultsHeight(Math.max(entry.contentRect.height - 34, 100))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [queryResult])

  useEffect(() => {
    const el = sidebarListRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      setSidebarHeight(entry.contentRect.height)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // 加载连接列表
  const loadConnections = useCallback(async () => {
    setConnectionsLoading(true)
    try {
      const data = await getDbConnections(1, 100)
      setConnections(data.items)
    } catch {
      getMessageInstance()?.error('加载连接列表失败')
    } finally {
      setConnectionsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadConnections()
  }, [loadConnections])

  const selectedConnection = connections.find((c) => c.id === selectedConnId)

  // 连接变更 → 加载表列表
  useEffect(() => {
    if (!selectedConnId) {
      setTables([])
      return
    }
    loadTableList(selectedConnId)
  }, [selectedConnId])

  const loadTableList = async (connId: string) => {
    setTablesLoading(true)
    try {
      const tableList = await listTables(connId)
      setTables(tableList)
    } catch {
      getMessageInstance()?.error('加载表列表失败')
      setTables([])
    } finally {
      setTablesLoading(false)
    }
  }

  // 分组 + 搜索过滤
  const { filteredGroups, filteredTotal } = useMemo(() => {
    const keyword = searchTableText.trim().toLowerCase()
    const filtered = keyword ? tables.filter((t) => t.name.toLowerCase().includes(keyword)) : tables

    // 按 schema 分组
    const groupMap: Record<string, TableInfo[]> = {}
    for (const t of filtered) {
      const schema = t.tableSchema || '默认'
      ;(groupMap[schema] ??= []).push(t)
    }
    // 排序：先按 schema 名排序，组内按表名排序
    const groups = Object.entries(groupMap)
      .sort(([a], [b]) => {
        if (a === '默认') return 1
        if (b === '默认') return -1
        return a.localeCompare(b)
      })
      .map(([schema, tables]) => ({
        schema,
        tables: tables.sort((a, b) => a.name.localeCompare(b.name)),
      }))

    return { filteredGroups: groups, filteredTotal: filtered.length }
  }, [tables, searchTableText])

  const showGroupHeaders = filteredGroups.length > 1

  // 摊平分组供虚拟列表渲染：分组头与表项交替的扁平结构
  const sidebarRows = useMemo(() => {
    const rows: SidebarRow[] = []
    for (const group of filteredGroups) {
      if (showGroupHeaders) {
        rows.push({
          kind: 'header',
          key: `h:${group.schema}`,
          schema: group.schema,
          count: group.tables.length,
        })
      }
      for (const table of group.tables) {
        rows.push({
          kind: 'table',
          key: `${group.schema}:${table.name}`,
          schema: group.schema,
          table,
          active: activeTableName === table.name,
        })
      }
    }
    return rows
  }, [filteredGroups, showGroupHeaders, activeTableName])

  // 单击/双击区分：双击前必然先触发两次单击，若单击立即弹窗，遮罩会吃掉第二次
  // 点击导致 onDoubleClick 永不触发。故单击延迟执行，双击到达时先取消。
  const clickTimerRef = useRef<number | null>(null)
  const clearClickTimer = useCallback(() => {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current)
      clickTimerRef.current = null
    }
  }, [])
  useEffect(() => clearClickTimer, [clearClickTimer])

  const openTableSchema = async (table: TableInfo) => {
    if (!selectedConnId) return
    setActiveTableName(table.name)
    setSchemaTableName(table.name)
    setSchemaModalOpen(true)
    setSchemaDetailLoading(true)
    try {
      const columns = await getTableSchema(
        selectedConnId,
        table.name,
        table.tableSchema ?? undefined,
      )
      setSchemaColumns(columns)
    } catch {
      getMessageInstance()?.error('加载列信息失败')
      setSchemaColumns([])
    } finally {
      setSchemaDetailLoading(false)
    }
  }

  // 单击表名（延迟 250ms）→ 弹窗展示列信息
  const handleTableClick = (table: TableInfo) => {
    clearClickTimer()
    clickTimerRef.current = window.setTimeout(() => {
      clickTimerRef.current = null
      openTableSchema(table)
    }, 250)
  }

  // 双击表名 → 插入 SELECT 语句。PG 的表按全 schema 列出，非默认 schema 的表
  // 必须带 schema 前缀，否则 search_path 解析不到（relation does not exist）
  const handleTableDoubleClick = (table: TableInfo) => {
    clearClickTimer()
    const dbType = selectedConnection?.dbType ?? 'postgresql'
    const quote = dbType === 'mysql' || dbType === 'doris' ? '`' : '"'
    const schema =
      dbType === 'postgresql' && table.tableSchema ? `${quote}${table.tableSchema}${quote}.` : ''
    setSql(`SELECT * FROM ${schema}${quote}${table.name}${quote} LIMIT 100`)
  }

  // 执行查询
  const handleExecute = async () => {
    if (!selectedConnId || !sql.trim()) return
    setQueryLoading(true)
    setQueryResult(null)
    try {
      const result = await executeQuery({
        connectionId: selectedConnId,
        sql: sql.trim(),
        maxRows,
        timeout,
      })
      setQueryResult(result)
      if (result.truncated) {
        getMessageInstance()?.warning(`结果已截断，仅显示前 ${result.rowCount} 行`)
      }
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      getMessageInstance()?.error(detail || '查询执行失败')
    } finally {
      setQueryLoading(false)
    }
  }

  // CSV 下载
  const handleDownloadCSV = () => {
    if (!queryResult) return
    const { columns, rows } = queryResult
    const csvContent =
      columns.map((c) => `"${c}"`).join(',') +
      '\n' +
      rows
        .map((row) => row.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(','))
        .join('\n')
    const blob = new Blob(['﻿' + csvContent], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `query_result_${dayjs().format('YYYYMMDD_HHmmss')}.csv`
    a.click()
    URL.revokeObjectURL(url)
    getMessageInstance()?.success('下载成功')
  }

  // 连接 CRUD
  const handleUpdateConnection = async (
    values: DbConnectionCreate | DbConnectionUpdate,
    id?: string,
  ) => {
    if (!id) return
    try {
      const { updateDbConnection } = await import('@/services/dataExplore')
      await updateDbConnection(id, values as DbConnectionUpdate)
      loadConnections()
      if (selectedConnId === id) {
        loadTableList(id)
      }
      getMessageInstance()?.success('连接已更新')
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      getMessageInstance()?.error(detail || '更新失败')
      throw err
    }
  }

  const handleDeleteConnection = async (id: string) => {
    try {
      await deleteDbConnection(id)
      if (selectedConnId === id) {
        setSelectedConnId(null)
        setTables([])
      }
      loadConnections()
      getMessageInstance()?.success('连接已删除')
    } catch {
      getMessageInstance()?.error('删除失败')
    }
  }

  const openCreateModal = () => {
    setEditingConnection(null)
    setConnModalOpen(true)
  }

  const openEditModal = (conn: DbConnection) => {
    setEditingConnection(conn)
    setConnModalOpen(true)
  }

  // 保存结果
  const handleSaveResult = async (targetPath: string, filename: string) => {
    if (!selectedConnId) return
    await saveQueryResult({
      connectionId: selectedConnId,
      sql: sql.trim(),
      targetPath,
      filename,
      format: filename.endsWith('.json') ? 'json' : 'csv',
    })
    getMessageInstance()?.success(`已保存到 ${targetPath}/${filename}`)
  }

  // 组装结果表格列（首列固定行号）
  const tableColumns = useMemo(() => {
    if (!queryResult) return []

    const rowNumCol = {
      title: '#',
      dataIndex: '__rowNum',
      key: '__rowNum',
      width: 56,
      fixed: 'left' as const,
      align: 'center' as const,
      render: (_: unknown, __: unknown, idx: number) => (
        <span style={{ color: '#999', fontSize: 12, userSelect: 'none' }}>{idx + 1}</span>
      ),
    }

    const dataCols = queryResult.columns.map((col, idx) => ({
      title: col,
      dataIndex: idx,
      key: String(idx),
      ellipsis: true,
      width: 150,
      render: (val: unknown) => (val === null ? <Tag color="default">NULL</Tag> : String(val)),
    }))

    return [rowNumCol, ...dataCols]
  }, [queryResult])

  const tableData = useMemo(
    () =>
      queryResult?.rows.map((row, rowIdx) => ({
        key: rowIdx,
        ...Object.fromEntries(row.map((cell, cellIdx) => [cellIdx, cell])),
      })) ?? [],
    [queryResult],
  )

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 112px)', gap: 1, background: '#f0f0f0' }}>
      {/* ====== 左栏：连接选择 + 表列表 ====== */}
      <div
        style={{
          width: 260,
          minWidth: 220,
          background: '#fff',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* 连接选择器区域 */}
        <div style={{ padding: '10px 12px 6px' }}>
          <Select
            style={{ width: '100%' }}
            placeholder="选择数据库连接"
            loading={connectionsLoading}
            value={selectedConnId}
            onChange={(val) => {
              setSelectedConnId(val)
              setActiveTableName(null)
              setSearchTableText('')
            }}
            options={connections.map((c) => ({
              value: c.id,
              label: (
                <span>
                  <Tag style={{ fontSize: 10 }}>{DB_TYPE_LABELS[c.dbType as DbType]}</Tag>
                  {c.name}
                </span>
              ),
            }))}
            popupRender={(menu) => (
              <>
                {menu}
                <div
                  style={{
                    display: 'flex',
                    gap: 4,
                    padding: 8,
                    borderTop: '1px solid #f0f0f0',
                  }}
                >
                  <Button
                    type="dashed"
                    size="small"
                    icon={<PlusOutlined />}
                    onClick={openCreateModal}
                    block
                  >
                    新建连接
                  </Button>
                </div>
              </>
            )}
          />
        </div>

        {/* 连接操作按钮 */}
        {selectedConnection && (
          <div style={{ padding: '0 12px 6px', display: 'flex', gap: 4 }}>
            <Tooltip title="编辑连接">
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEditModal(selectedConnection)}
              />
            </Tooltip>
            <Popconfirm
              title="确定删除此连接？"
              onConfirm={() => handleDeleteConnection(selectedConnection.id)}
            >
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
            <Tooltip title="刷新表列表">
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => loadTableList(selectedConnection.id)}
              />
            </Tooltip>
          </div>
        )}

        {/* 分隔 */}
        <div style={{ borderTop: '1px solid #f0f0f0' }} />

        {/* 搜索框 */}
        {selectedConnId && tables.length > 0 && (
          <div style={{ padding: '8px 12px' }}>
            <Input
              size="small"
              prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="搜索表名..."
              value={searchTableText}
              onChange={(e) => setSearchTableText(e.target.value)}
              allowClear
            />
          </div>
        )}

        {/* 表统计 */}
        {selectedConnId && !tablesLoading && tables.length > 0 && (
          <div style={{ padding: '0 12px 4px' }}>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {searchTableText
                ? `匹配 ${filteredTotal} / ${tables.length} 张表`
                : tables.length >= TABLE_LIST_LIMIT
                  ? `${tables.length} 张表（已达单次上限）`
                  : `共 ${tables.length} 张表`}
            </Typography.Text>
          </div>
        )}

        {/* 表列表（虚拟滚动：大库数千表不整树渲染） */}
        <div ref={sidebarListRef} style={{ flex: 1, overflow: 'hidden', padding: '0 8px 8px' }}>
          {tablesLoading ? (
            <Spin tip="加载中..." style={{ display: 'block', padding: 20 }}>
              <div style={{ height: 50 }} />
            </Spin>
          ) : selectedConnId && filteredGroups.length === 0 && searchTableText ? (
            <Typography.Text
              type="secondary"
              style={{ fontSize: 12, padding: '16px 4px', display: 'block', textAlign: 'center' }}
            >
              未找到匹配的表
            </Typography.Text>
          ) : selectedConnId && tables.length === 0 ? (
            <Typography.Text
              type="secondary"
              style={{ fontSize: 12, padding: '16px 4px', display: 'block', textAlign: 'center' }}
            >
              暂无表数据
            </Typography.Text>
          ) : !selectedConnId ? (
            <Typography.Text
              type="secondary"
              style={{ fontSize: 12, padding: '16px 4px', display: 'block', textAlign: 'center' }}
            >
              请先选择或新建数据库连接
            </Typography.Text>
          ) : (
            <VirtualList
              data={sidebarRows}
              height={sidebarHeight}
              itemHeight={SIDEBAR_ROW_HEIGHT}
              itemKey="key"
            >
              {(row: SidebarRow) =>
                row.kind === 'header' ? (
                  <div
                    style={{
                      height: SIDEBAR_ROW_HEIGHT,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '0 4px',
                      margin: '0 8px',
                      fontSize: 11,
                      fontWeight: 600,
                      color: '#8c8c8c',
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                    }}
                  >
                    <FolderOutlined style={{ fontSize: 12 }} />
                    <span style={{ flex: 1 }}>{row.schema}</span>
                    <span style={{ fontWeight: 400, color: '#bfbfbf' }}>{row.count}</span>
                  </div>
                ) : (
                  <div
                    onClick={() => handleTableClick(row.table)}
                    onDoubleClick={() => handleTableDoubleClick(row.table)}
                    title="单击查看结构，双击插入 SELECT"
                    style={{
                      height: SIDEBAR_ROW_HEIGHT,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '0 8px',
                      margin: '0 8px',
                      marginLeft: showGroupHeaders ? 14 : 8,
                      borderRadius: 6,
                      cursor: 'pointer',
                      border: row.active ? '1px solid #91caff' : '1px solid transparent',
                      background: row.active ? '#e6f4ff' : 'transparent',
                      transition: 'background 0.15s, border-color 0.15s',
                      fontSize: 13,
                      lineHeight: '22px',
                    }}
                    onMouseEnter={(e) => {
                      if (!row.active) {
                        e.currentTarget.style.background = '#f5f5f5'
                        e.currentTarget.style.borderColor = '#e8e8e8'
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!row.active) {
                        e.currentTarget.style.background = 'transparent'
                        e.currentTarget.style.borderColor = 'transparent'
                      }
                    }}
                  >
                    {row.table.type === 'view' ? (
                      <FileTextOutlined style={{ fontSize: 12, color: '#fa8c16', flexShrink: 0 }} />
                    ) : (
                      <TableOutlined style={{ fontSize: 12, color: '#1890ff', flexShrink: 0 }} />
                    )}
                    <Typography.Text
                      ellipsis
                      style={{
                        flex: 1,
                        fontSize: 13,
                        fontWeight: row.active ? 500 : 400,
                        color: row.active ? '#1890ff' : undefined,
                      }}
                    >
                      {row.table.name}
                    </Typography.Text>
                    <Tag
                      style={{
                        fontSize: 10,
                        lineHeight: '16px',
                        padding: '0 4px',
                        margin: 0,
                        flexShrink: 0,
                      }}
                      color={row.table.type === 'view' ? 'orange' : 'default'}
                    >
                      {row.table.type === 'view' ? '视图' : '表'}
                    </Tag>
                  </div>
                )
              }
            </VirtualList>
          )}
        </div>
      </div>

      {/* ====== 中栏：SQL 编辑器 + 操作栏 + 结果 ====== */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          background: '#fff',
          minWidth: 300,
        }}
      >
        {/* 顶部信息栏 */}
        <div
          style={{
            padding: '8px 12px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          {selectedConnection && (
            <>
              <Tag color="blue">{DB_TYPE_LABELS[selectedConnection.dbType as DbType]}</Tag>
              <Typography.Text strong>{selectedConnection.name}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {selectedConnection.host}:{selectedConnection.port}/
                {selectedConnection.databaseName}
              </Typography.Text>
            </>
          )}
        </div>

        {/* SQL 编辑器 */}
        <div style={{ flex: 1, minHeight: 200 }}>
          <SqlEditor value={sql} onChange={setSql} />
        </div>

        {/* 操作栏 */}
        <div
          style={{
            padding: '8px 12px',
            borderTop: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          <Button
            type="primary"
            icon={queryLoading ? <StopOutlined /> : <PlayCircleOutlined />}
            onClick={handleExecute}
            loading={queryLoading}
            disabled={!selectedConnId || !sql.trim()}
          >
            执行
          </Button>

          <Space size={4}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              最大行数：
            </Typography.Text>
            <InputNumber
              size="small"
              min={1}
              max={10000}
              value={maxRows}
              onChange={(v) => setMaxRows(v ?? 1000)}
              style={{ width: 80 }}
            />
          </Space>

          <Space size={4}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              超时(秒)：
            </Typography.Text>
            <InputNumber
              size="small"
              min={1}
              max={300}
              value={timeout}
              onChange={(v) => setTimeout_(v ?? 30)}
              style={{ width: 70 }}
            />
          </Space>

          <div style={{ flex: 1 }} />

          <Button
            icon={<DownloadOutlined />}
            onClick={handleDownloadCSV}
            disabled={!queryResult || queryResult.rowCount === 0}
          >
            下载 CSV
          </Button>

          <Button
            icon={<FolderOpenOutlined />}
            onClick={() => setSaveModalOpen(true)}
            disabled={!selectedConnId || !sql.trim()}
          >
            保存到平台
          </Button>
        </div>

        {/* 结果表格 */}
        <div
          ref={resultsContainerRef}
          style={{ flex: 1, minHeight: 150, overflow: 'hidden', borderTop: '1px solid #f0f0f0' }}
        >
          {queryLoading ? (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100%',
              }}
            >
              <Spin tip="查询中...">
                <div style={{ height: 50 }} />
              </Spin>
            </div>
          ) : queryResult ? (
            <>
              <Table
                virtual
                columns={tableColumns}
                dataSource={tableData}
                size="small"
                scroll={{ x: 'max-content', y: resultsHeight }}
                pagination={false}
                bordered
                showSorterTooltip={false}
                locale={{ emptyText: '查询结果为空' }}
              />
              <div
                style={{
                  padding: '6px 12px',
                  borderTop: '1px solid #f0f0f0',
                  fontSize: 12,
                  color: '#888',
                  display: 'flex',
                  justifyContent: 'space-between',
                  flexShrink: 0,
                }}
              >
                <span>
                  返回 <strong style={{ color: '#1890ff' }}>{queryResult.rowCount}</strong> 行
                  {queryResult.truncated ? (
                    <Tag
                      color="warning"
                      style={{ marginLeft: 6, fontSize: 11, lineHeight: '16px' }}
                    >
                      已截断
                    </Tag>
                  ) : null}
                </span>
                <span>
                  耗时{' '}
                  <strong
                    style={{ color: queryResult.executionTimeMs > 1000 ? '#ff4d4f' : '#52c41a' }}
                  >
                    {queryResult.executionTimeMs >= 1000
                      ? `${(queryResult.executionTimeMs / 1000).toFixed(1)}s`
                      : `${queryResult.executionTimeMs}ms`}
                  </strong>
                </span>
              </div>
            </>
          ) : (
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                height: '100%',
                color: '#bbb',
              }}
            >
              点击「执行」查看查询结果
            </div>
          )}
        </div>
      </div>

      {/* ====== Table Schema 弹窗 ====== */}
      <Modal
        title={
          <Space>
            <TableOutlined />
            <span>{schemaTableName}</span>
            <Tag color="blue">{schemaColumns.length} 列</Tag>
          </Space>
        }
        open={schemaModalOpen}
        onCancel={() => setSchemaModalOpen(false)}
        width="fit-content"
        styles={{ body: { maxWidth: '80vw', maxHeight: '70vh', overflow: 'auto', padding: 0 } }}
        footer={null}
      >
        <Spin spinning={schemaDetailLoading}>
          {schemaColumns.length > 0 ? (
            <Table
              dataSource={schemaColumns}
              rowKey="name"
              size="small"
              pagination={false}
              columns={[
                {
                  title: '列名',
                  dataIndex: 'name',
                  key: 'name',
                  width: 200,
                  render: (name: string, record: ColumnInfo) => (
                    <Space size={4}>
                      {record.isPrimaryKey && (
                        <Tag color="blue" style={{ fontSize: 10 }}>
                          PK
                        </Tag>
                      )}
                      <Typography.Text code>{name}</Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '数据类型',
                  dataIndex: 'dataType',
                  key: 'dataType',
                  width: 160,
                  render: (dt: string) => <Tag>{dt}</Tag>,
                },
                {
                  title: '可空',
                  dataIndex: 'nullable',
                  key: 'nullable',
                  width: 70,
                  align: 'center',
                  render: (v: boolean) =>
                    v ? 'YES' : <Typography.Text type="secondary">NO</Typography.Text>,
                },
                {
                  title: '默认值',
                  dataIndex: 'defaultValue',
                  key: 'defaultValue',
                  width: 160,
                  render: (v: string | null) =>
                    v !== null && v !== undefined ? (
                      <Typography.Text code>{v}</Typography.Text>
                    ) : (
                      <Typography.Text type="secondary">—</Typography.Text>
                    ),
                },
                {
                  title: '注释',
                  dataIndex: 'comment',
                  key: 'comment',
                  ellipsis: true,
                  render: (v: string | null) =>
                    v ? <span>{v}</span> : <Typography.Text type="secondary">—</Typography.Text>,
                },
              ]}
            />
          ) : (
            !schemaDetailLoading && (
              <Typography.Text
                type="secondary"
                style={{ display: 'block', padding: 40, textAlign: 'center' }}
              >
                该表无列信息或加载失败
              </Typography.Text>
            )
          )}
        </Spin>
      </Modal>

      {/* ====== 连接表单 Modal ====== */}
      <ConnectionFormModal
        open={connModalOpen}
        editingConnection={editingConnection}
        onClose={() => setConnModalOpen(false)}
        onSuccess={
          editingConnection
            ? (values, id) => handleUpdateConnection(values, id)
            : async (values) => {
                const { createDbConnection } = await import('@/services/dataExplore')
                await createDbConnection(values as DbConnectionCreate)
                loadConnections()
                getMessageInstance()?.success('连接创建成功')
              }
        }
      />

      {/* ====== 保存结果 Modal ====== */}
      {selectedConnId && (
        <SaveToFileModal
          open={saveModalOpen}
          onClose={() => setSaveModalOpen(false)}
          onSave={handleSaveResult}
        />
      )}
    </div>
  )
}
