import { describe, it, expect } from 'vitest'
import { toTableData } from '@/pages/annotations/components/viewers/tableData'

describe('toTableData — JSON 对象数组', () => {
  it('按对象键生成列', () => {
    const { columns, rows } = toTableData(
      [
        { a: 1, b: 'x' },
        { a: 2, b: 'y' },
      ],
      ',',
    )
    expect(columns.map((c) => c.dataIndex)).toEqual(['a', 'b'])
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({ a: 1, b: 'x' })
  })

  it('合并所有行的键（稀疏对象）', () => {
    const { columns } = toTableData([{ a: 1 }, { b: 2 }], ',')
    expect(columns.map((c) => c.dataIndex).sort()).toEqual(['a', 'b'])
  })
})

describe('toTableData — CSV 字符串', () => {
  it('首行表头，逗号分隔', () => {
    const { columns, rows } = toTableData('name,age\nalice,30\nbob,25', ',')
    expect(columns.map((c) => c.title)).toEqual(['name', 'age'])
    expect(rows).toEqual([
      { name: 'alice', age: '30' },
      { name: 'bob', age: '25' },
    ])
  })

  it('自定义分隔符', () => {
    const { rows } = toTableData('a;b\n1;2', ';')
    expect(rows).toEqual([{ a: '1', b: '2' }])
  })

  it('单行 CSV 不生成表格', () => {
    expect(toTableData('onlyheader', ',').rows).toHaveLength(0)
  })
})

describe('toTableData — 二维数组', () => {
  it('首行作为表头', () => {
    const { columns, rows } = toTableData(
      [
        ['x', 'y'],
        [1, 2],
        [3, 4],
      ],
      ',',
    )
    expect(columns.map((c) => c.title)).toEqual(['x', 'y'])
    expect(rows).toHaveLength(2)
  })
})

describe('toTableData — 边界', () => {
  it('非表格数据返回空', () => {
    expect(toTableData(undefined, ',').rows).toHaveLength(0)
    expect(toTableData('just text', ',').rows).toHaveLength(0)
    expect(toTableData([], ',').rows).toHaveLength(0)
  })
})
