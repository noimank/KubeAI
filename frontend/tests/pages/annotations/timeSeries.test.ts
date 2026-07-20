import { describe, it, expect } from 'vitest'
import {
  parseTimeSeriesCSV,
  parseTimeSeriesJSON,
  parseTimeSeriesData,
  isUrlValue,
} from '@/pages/annotations/utils/timeSeries'

describe('parseTimeSeriesCSV', () => {
  it('解析带 timeColumn 的 CSV', () => {
    const csv = 'time,velocity\n1,10\n2,20\n3,30'
    const r = parseTimeSeriesCSV(csv, { timeColumn: 'time' })
    expect(r?.times).toEqual([1, 2, 3])
    expect(r?.channels).toEqual([{ column: 'velocity', values: [10, 20, 30] }])
  })

  it('自定义 sep', () => {
    const r = parseTimeSeriesCSV('t;a;b\n0;1;2', { sep: ';', timeColumn: 't' })
    expect(r?.times).toEqual([0])
    expect(r?.channels.map((c) => c.column)).toEqual(['a', 'b'])
  })

  it('无 timeColumn → 行索引作时间', () => {
    const r = parseTimeSeriesCSV('v\n10\n20', {})
    expect(r?.times).toEqual([0, 1])
    expect(r?.channels[0].values).toEqual([10, 20])
  })

  it('时间列为日期字符串 → Date.parse 时间戳', () => {
    const r = parseTimeSeriesCSV('time,v\n2020-01-01,1', { timeColumn: 'time' })
    expect(r?.times[0]).toBe(Date.parse('2020-01-01'))
  })

  it('单行无数据 → null', () => {
    expect(parseTimeSeriesCSV('time,v', { timeColumn: 'time' })).toBeNull()
  })
})

describe('parseTimeSeriesJSON', () => {
  it('对象数组', () => {
    const r = parseTimeSeriesJSON(
      [
        { t: 1, a: 5 },
        { t: 2, a: 6 },
      ],
      { timeColumn: 't' },
    )
    expect(r?.times).toEqual([1, 2])
    expect(r?.channels).toEqual([{ column: 'a', values: [5, 6] }])
  })
})

describe('parseTimeSeriesData', () => {
  it('JSON 字符串', () => {
    const r = parseTimeSeriesData('[{"t":0,"v":1}]', { timeColumn: 't' })
    expect(r?.channels[0].values).toEqual([1])
  })
  it('CSV 字符串', () => {
    const r = parseTimeSeriesData('time,v\n0,9', { timeColumn: 'time' })
    expect(r?.times).toEqual([0])
  })
  it('null → null', () => {
    expect(parseTimeSeriesData(null)).toBeNull()
  })
})

describe('isUrlValue', () => {
  it('识别 URL / 路径', () => {
    expect(isUrlValue('https://x/y.csv')).toBe(true)
    expect(isUrlValue('/api/data.csv')).toBe(true)
    expect(isUrlValue('time,v\n0,1')).toBe(false)
  })
})
