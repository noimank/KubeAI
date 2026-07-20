import { useMemo } from 'react'
import { Table, Typography } from 'antd'
import { toTableData } from './tableData'

/**
 * Table 对象查看器 —— 渲染表格数据（JSON 数组或 CSV 字符串）。
 * 解析逻辑见 tableData.ts。
 */
export default function TableView({ value, sep = ',' }: { value: unknown; sep?: string }) {
  const { columns, rows } = useMemo(() => toTableData(value, sep), [value, sep])

  if (rows.length === 0) {
    return <Typography.Text type="secondary">无表格数据</Typography.Text>
  }

  return (
    <Table
      size="small"
      columns={columns}
      dataSource={rows}
      rowKey={(_record, index) => String(index)}
      pagination={rows.length > 10 ? { pageSize: 10 } : false}
      scroll={{ x: 'max-content' }}
    />
  )
}
