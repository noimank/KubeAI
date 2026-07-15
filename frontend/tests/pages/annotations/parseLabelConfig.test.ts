import { describe, it, expect } from 'vitest'
import { parseLabelConfig, taxonomyToTreeData } from '@/pages/annotations/utils/parseLabelConfig'

describe('parseLabelConfig - Taxonomy 嵌套树', () => {
  const taxonomyXml = `<View>
    <Text name="text" value="$text"/>
    <Taxonomy name="tax" toName="text">
      <Choice value="动物">
        <Choice value="哺乳动物">
          <Choice value="猫"/>
          <Choice value="狗"/>
        </Choice>
        <Choice value="鸟类">
          <Choice value="鹰"/>
        </Choice>
      </Choice>
      <Choice value="植物">
        <Choice value="乔木"/>
        <Choice value="草本"/>
      </Choice>
    </Taxonomy>
  </View>`

  it('递归构建嵌套 Choice 树', () => {
    const parsed = parseLabelConfig(taxonomyXml)
    const tax = parsed.controls.find((c) => c.type === 'taxonomy')
    expect(tax).toBeDefined()
    expect(tax?.taxonomy).toEqual([
      {
        value: '动物',
        children: [
          {
            value: '哺乳动物',
            children: [
              { value: '猫', children: [] },
              { value: '狗', children: [] },
            ],
          },
          { value: '鸟类', children: [{ value: '鹰', children: [] }] },
        ],
      },
      {
        value: '植物',
        children: [
          { value: '乔木', children: [] },
          { value: '草本', children: [] },
        ],
      },
    ])
  })

  it('非 Taxonomy 控件不解析 taxonomy 字段', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Choices name="c" toName="image">
        <Choice value="A"/>
        <Choice value="B"/>
      </Choices>
    </View>`
    const parsed = parseLabelConfig(xml)
    const choices = parsed.controls.find((c) => c.type === 'choices')
    expect(choices?.taxonomy).toBeUndefined()
  })

  it('taxonomyToTreeData 转换为 antd TreeSelect 格式', () => {
    const parsed = parseLabelConfig(taxonomyXml)
    const tax = parsed.controls.find((c) => c.type === 'taxonomy')
    const tree = taxonomyToTreeData(tax?.taxonomy)
    expect(tree).toHaveLength(2)
    expect(tree[0]).toMatchObject({ value: '动物', title: '动物' })
    expect(tree[0].children).toHaveLength(2)
    expect(tree[0].children?.[0]).toMatchObject({ value: '哺乳动物', title: '哺乳动物' })
    expect(tree[0].children?.[0].children).toHaveLength(2)
  })
})

describe('parseLabelConfig - 控制类型路由', () => {
  it('正确解析 choices 标签', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Choices name="c" toName="image" choice="multiple">
        <Choice value="A"/>
        <Choice value="B"/>
      </Choices>
    </View>`
    const parsed = parseLabelConfig(xml)
    expect(parsed.controls).toHaveLength(1)
    expect(parsed.controls[0].type).toBe('choices')
    expect(parsed.controls[0].choice).toBe('multiple')
    expect(parsed.labels).toEqual(['A', 'B'])
  })

  it('缺少数据标签返回 error', () => {
    const xml = `<View><Choices name="c" toName="missing"><Choice value="A"/></Choices></View>`
    const parsed = parseLabelConfig(xml)
    expect(parsed.error).toBe('配置缺少数据标签')
  })

  it('无效 XML 返回 error', () => {
    const parsed = parseLabelConfig('<not closed')
    expect(parsed.error).toBe('标注配置 XML 格式无效')
  })
})

describe('parseLabelConfig - 无标签几何控件', () => {
  it('解析 Rectangle（无 Labels 后缀）', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Rectangle name="box" toName="image" />
      <TextArea name="transcription" toName="image" perRegion="true" />
    </View>`
    const parsed = parseLabelConfig(xml)
    expect(parsed.controls).toHaveLength(2)
    const rect = parsed.controls.find((c) => c.type === 'rectangle')
    expect(rect).toBeDefined()
    expect(rect?.tag).toBe('Rectangle')
    expect(rect?.choices).toEqual([])
  })

  it('解析多个无标签几何控件', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Rectangle name="r1" toName="image" />
      <Polygon name="p1" toName="image" />
      <KeyPoint name="kp1" toName="image" />
      <Ellipse name="e1" toName="image" />
      <Brush name="b1" toName="image" />
    </View>`
    const parsed = parseLabelConfig(xml)
    const types = parsed.controls.map((c) => c.type)
    expect(types).toContain('rectangle')
    expect(types).toContain('polygon')
    expect(types).toContain('keypoint')
    expect(types).toContain('ellipse')
    expect(types).toContain('brush')
  })
})

describe('parseLabelConfig - perRegion 属性解析', () => {
  it('解析 perRegion="true"', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Rectangle name="box" toName="image" />
      <TextArea name="label" toName="image" perRegion="true" />
    </View>`
    const parsed = parseLabelConfig(xml)
    const ta = parsed.controls.find((c) => c.type === 'textarea')
    expect(ta?.perRegion).toBe(true)
  })

  it('perRegion 默认 false', () => {
    const xml = `<View>
      <Text name="text" value="$text"/>
      <TextArea name="label" toName="text" />
    </View>`
    const parsed = parseLabelConfig(xml)
    const ta = parsed.controls.find((c) => c.type === 'textarea')
    expect(ta?.perRegion).toBeFalsy()
  })

  it('解析 perRegion Choices', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <RectangleLabels name="tag" toName="image">
        <Label value="Car"/>
      </RectangleLabels>
      <Choices name="color" toName="image" perRegion="true">
        <Choice value="Red"/>
        <Choice value="Blue"/>
      </Choices>
    </View>`
    const parsed = parseLabelConfig(xml)
    const choices = parsed.controls.find((c) => c.type === 'choices')
    expect(choices?.perRegion).toBe(true)
    expect(choices?.choices).toEqual([{ value: 'Red' }, { value: 'Blue' }])
  })

  it('解析 whenLabelValue 和 displayMode', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Rectangle name="box" toName="image" />
      <TextArea name="transcription" toName="image" perRegion="true"
        whenLabelValue="Text" displayMode="region-list" />
    </View>`
    const parsed = parseLabelConfig(xml)
    const ta = parsed.controls.find((c) => c.type === 'textarea')
    expect(ta?.perRegion).toBe(true)
    expect(ta?.whenLabelValue).toBe('Text')
    expect(ta?.displayMode).toBe('region-list')
  })
})
