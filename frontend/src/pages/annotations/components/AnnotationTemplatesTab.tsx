import { useState, useMemo } from 'react'
import {
  Button,
  Card,
  Checkbox,
  Collapse,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { DeleteOutlined, EditOutlined, ImportOutlined, PlusOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createAnnotationTemplate,
  deleteAnnotationTemplate,
  listAnnotationTemplateGroups,
  listAnnotationTemplates,
  listLsImportableTemplates,
} from '@/services/annotation-templates'
import { getMessageInstance } from '@/utils/messageHolder'
import TemplateBuilder from './TemplateBuilder'
import type { AnnotationTemplate, AnnotationTemplateImportItem } from '@/types/annotation-template'

interface AnnotationTemplatesTabProps {
  canWrite: boolean
}

export default function AnnotationTemplatesTab({ canWrite }: AnnotationTemplatesTabProps) {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [editing, setEditing] = useState<{ open: boolean; id?: string }>({ open: false })
  const [importOpen, setImportOpen] = useState(false)
  const [checkedKeys, setCheckedKeys] = useState<string[]>([])
  const [importing, setImporting] = useState(false)
  const queryClient = useQueryClient()

  const [filterGroup, setFilterGroup] = useState<string | undefined>()

  const { data, isFetching } = useQuery({
    queryKey: ['annotationTemplates', page, pageSize, keyword, filterGroup],
    queryFn: () =>
      listAnnotationTemplates({
        current: page,
        pageSize,
        name: keyword || undefined,
        group: filterGroup,
      }),
  })

  const { data: groups } = useQuery({
    queryKey: ['annotationTemplateGroups'],
    queryFn: listAnnotationTemplateGroups,
    staleTime: 60_000,
  })

  const { data: lsImports, isFetching: isLsImportsLoading } = useQuery({
    queryKey: ['lsImports'],
    queryFn: listLsImportableTemplates,
    staleTime: 5 * 60 * 1000,
  })

  const lsGrouped = useMemo(() => {
    if (!lsImports) return {}
    const map: Record<string, AnnotationTemplateImportItem[]> = {}
    for (const item of lsImports) {
      const g = item.group || '其他'
      if (!map[g]) map[g] = []
      map[g].push(item)
    }
    return map
  }, [lsImports])

  const allLsKeys = useMemo(() => (lsImports ?? []).map((i) => i.key), [lsImports])

  const handleImport = async () => {
    if (checkedKeys.length === 0) return
    setImporting(true)
    let ok = 0
    let fail = 0
    for (const key of checkedKeys) {
      const item = (lsImports ?? []).find((i) => i.key === key)
      if (!item) continue
      try {
        await createAnnotationTemplate({
          name: item.label,
          description: item.description,
          labelConfig: item.config,
          tags: [],
          group: item.group,
        })
        ok++
      } catch {
        fail++
      }
    }
    setImporting(false)
    setImportOpen(false)
    setCheckedKeys([])
    getMessageInstance()?.success(`导入完成: 成功 ${ok}, 失败 ${fail}`)
    queryClient.invalidateQueries({ queryKey: ['annotationTemplates'] })
    queryClient.invalidateQueries({ queryKey: ['annotationTemplateGroups'] })
  }

  const handleDelete = (row: AnnotationTemplate) => {
    Modal.confirm({
      title: '确认删除模板?',
      content: '若模板被项目引用将无法删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteAnnotationTemplate(row.id)
          getMessageInstance()?.success('已删除')
          queryClient.invalidateQueries({ queryKey: ['annotationTemplates'] })
          queryClient.invalidateQueries({ queryKey: ['annotationTemplateGroups'] })
        } catch (e) {
          getMessageInstance()?.error((e as Error & { message?: string }).message ?? '删除失败')
        }
      },
    })
  }

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <Space>
          <Input.Search
            placeholder="按名称搜索"
            allowClear
            style={{ width: 220 }}
            onSearch={(v) => {
              setKeyword(v)
              setPage(1)
            }}
          />
          <Select
            placeholder="分组筛选"
            allowClear
            style={{ width: 160 }}
            value={filterGroup}
            onChange={(v) => {
              setFilterGroup(v)
              setPage(1)
            }}
            options={(groups ?? []).map((g) => ({ value: g, label: g }))}
          />
        </Space>

        {canWrite && (
          <Space>
            <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>
              模板市场
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setEditing({ open: true })}
            >
              新建模板
            </Button>
          </Space>
        )}
      </Space>

      <Table
        loading={isFetching}
        dataSource={data?.items ?? []}
        rowKey="id"
        columns={[
          { title: '名称', dataIndex: 'name' },
          { title: '描述', dataIndex: 'description', ellipsis: true },
          {
            title: '分组',
            dataIndex: 'group',
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: '标签',
            dataIndex: 'tags',
            render: (tags: string[]) =>
              tags?.length ? tags.map((t) => <Tag key={t}>{t}</Tag>) : '-',
          },
          { title: '创建时间', dataIndex: 'createdAt' },
          {
            title: '操作',
            key: 'op',
            render: (_: unknown, row: AnnotationTemplate) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  disabled={!canWrite}
                  onClick={() => setEditing({ open: true, id: row.id })}
                >
                  编辑
                </Button>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={!canWrite}
                  onClick={() => handleDelete(row)}
                >
                  删除
                </Button>
              </Space>
            ),
          },
        ]}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
      />

      {/* 新建/编辑 */}
      <Modal
        open={editing.open}
        title={editing.id ? '编辑标注模板' : '新建标注模板'}
        footer={null}
        width={1100}
        destroyOnHidden
        onCancel={() => setEditing({ open: false })}
      >
        <TemplateBuilder
          templateId={editing.id}
          onSaved={() => {
            setEditing({ open: false })
            queryClient.invalidateQueries({ queryKey: ['annotationTemplates'] })
          }}
        />
      </Modal>

      {/* 模板市场 */}
      <Modal
        open={importOpen}
        title="模板市场"
        okText="导入选中"
        cancelText="取消"
        confirmLoading={importing}
        onOk={handleImport}
        onCancel={() => {
          setImportOpen(false)
          setCheckedKeys([])
        }}
        width={700}
      >
        {isLsImportsLoading ? (
          '加载中...'
        ) : (
          <Collapse
            items={Object.entries(lsGrouped).map(([group, items]) => ({
              key: group,
              label: `${group} (${items.length})`,
              children: (
                <Checkbox.Group
                  value={checkedKeys}
                  onChange={(vals) => setCheckedKeys(vals as string[])}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {items.map((item) => (
                      <Checkbox key={item.key} value={item.key}>
                        <Space direction="vertical" size={0}>
                          <strong>{item.label}</strong>
                          <Typography.Paragraph
                            type="secondary"
                            style={{ fontSize: 12, margin: 0 }}
                          >
                            {item.description}
                          </Typography.Paragraph>
                        </Space>
                      </Checkbox>
                    ))}
                  </Space>
                </Checkbox.Group>
              ),
            }))}
          />
        )}
        <div style={{ marginTop: 12 }}>
          <Space>
            <Button size="small" onClick={() => setCheckedKeys(allLsKeys)}>
              全选
            </Button>
            <Button size="small" onClick={() => setCheckedKeys([])}>
              取消全选
            </Button>
          </Space>
        </div>
      </Modal>
    </Card>
  )
}
