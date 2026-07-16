import { describe, it, expect } from 'vitest'
import {
  parseConfigTree,
  findNodes,
  findFirstNode,
  taxonomyToTreeData,
  toControlConfig,
  toObjectConfig,
} from '@/pages/annotations/utils/parseLabelConfig'

describe('parseConfigTree — 树形解析', () => {
  it('解析基本结构', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Choices name="category" toName="image">
        <Choice value="A"/>
        <Choice value="B"/>
      </Choices>
    </View>`
    const root = parseConfigTree(xml)
    expect(root.tag).toBe('View')
    expect(root.children).toHaveLength(2)
    expect(root.children[0].tag).toBe('Image')
    expect(root.children[0].type).toBe('object')
    expect(root.children[1].tag).toBe('Choices')
    expect(root.children[1].type).toBe('control')
  })

  it('保留树层级结构', () => {
    const xml = `<View>
      <Header value="标题" size="3"/>
      <View style="display: flex;">
        <Image name="img" value="$image"/>
        <Choices name="cat" toName="img">
          <Choice value="X"/>
        </Choices>
      </View>
    </View>`
    const root = parseConfigTree(xml)
    expect(root.children).toHaveLength(2)
    const innerView = root.children[1]
    expect(innerView.tag).toBe('View')
    expect(innerView.attrs.style).toBe('display: flex;')
    expect(innerView.children).toHaveLength(2)
    expect(innerView.children[0].tag).toBe('Image')
    expect(innerView.children[1].tag).toBe('Choices')
  })

  it('解析 Header 标签', () => {
    const xml = `<View><Header value="Hello" size="4"/></View>`
    const root = parseConfigTree(xml)
    const header = root.children[0]
    expect(header.tag).toBe('Header')
    expect(header.type).toBe('visual')
    expect(header.attrs.value).toBe('Hello')
    expect(header.attrs.size).toBe('4')
  })

  it('解析 Markdown 标签', () => {
    const xml = `<View><Markdown>## 说明\n请仔细阅读</Markdown></View>`
    const root = parseConfigTree(xml)
    const md = root.children[0]
    expect(md.tag).toBe('Markdown')
    expect(md.text).toContain('## 说明')
  })

  it('解析 Style 标签', () => {
    const xml = `<View><Style>.cls { color: red; }</Style></View>`
    const root = parseConfigTree(xml)
    const style = root.children[0]
    expect(style.tag).toBe('Style')
    expect(style.text).toContain('.cls { color: red; }')
  })

  it('解析 Collapse + Panel', () => {
    const xml = `<View>
      <Collapse accordion="true" bordered="false">
        <Panel value="面板1">
          <Choices name="c1" toName="img">
            <Choice value="A"/>
          </Choices>
        </Panel>
        <Panel value="面板2">
          <TextArea name="t1" toName="img"/>
        </Panel>
      </Collapse>
    </View>`
    const root = parseConfigTree(xml)
    const collapse = root.children[0]
    expect(collapse.tag).toBe('Collapse')
    expect(collapse.children).toHaveLength(2)
    expect(collapse.children[0].tag).toBe('Panel')
    expect(collapse.children[0].attrs.value).toBe('面板1')
    expect(collapse.children[0].children[0].tag).toBe('Choices')
  })

  it('无效 XML 抛出异常', () => {
    expect(() => parseConfigTree('<not closed')).toThrow('XML 格式无效')
  })
})

describe('findNodes / findFirstNode', () => {
  const xml = `<View>
    <Image name="img" value="$image"/>
    <Choices name="c1" toName="img"><Choice value="A"/></Choices>
    <Choices name="c2" toName="img"><Choice value="B"/></Choices>
    <TextArea name="t1" toName="img"/>
  </View>`

  it('findNodes 按 predicate 过滤', () => {
    const root = parseConfigTree(xml)
    const choices = findNodes(root, (n) => n.tag === 'Choices')
    expect(choices).toHaveLength(2)
    expect(choices.map((c) => c.name)).toEqual(['c1', 'c2'])
  })

  it('findFirstNode 返回第一个匹配', () => {
    const root = parseConfigTree(xml)
    const first = findFirstNode(root, (n) => n.tag === 'Choices')
    expect(first?.name).toBe('c1')
  })

  it('findNodes 按 controlType 过滤', () => {
    const root = parseConfigTree(xml)
    const controls = findNodes(root, (n) => n.controlType === 'choices')
    expect(controls).toHaveLength(2)
  })
})

describe('Taxonomy 嵌套树', () => {
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
    const root = parseConfigTree(taxonomyXml)
    const tax = findFirstNode(root, (n) => n.tag === 'Taxonomy')
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
        <Choice value="A"/><Choice value="B"/>
      </Choices>
    </View>`
    const root = parseConfigTree(xml)
    const choices = findFirstNode(root, (n) => n.tag === 'Choices')
    expect(choices?.taxonomy).toBeUndefined()
  })

  it('taxonomyToTreeData 转换为 antd TreeSelect 格式', () => {
    const root = parseConfigTree(taxonomyXml)
    const tax = findFirstNode(root, (n) => n.tag === 'Taxonomy')
    const tree = taxonomyToTreeData(tax?.taxonomy)
    expect(tree).toHaveLength(2)
    expect(tree[0]).toMatchObject({ value: '动物', title: '动物' })
    expect(tree[0].children).toHaveLength(2)
  })
})

describe('toControlConfig / toObjectConfig', () => {
  it('toControlConfig 生成正确结构', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Choices name="c" toName="image" choice="multiple">
        <Choice value="A"/>
        <Choice value="B"/>
      </Choices>
    </View>`
    const root = parseConfigTree(xml)
    const node = findFirstNode(root, (n) => n.tag === 'Choices')!
    const config = toControlConfig(node)
    expect(config.tag).toBe('Choices')
    expect(config.name).toBe('c')
    expect(config.toName).toBe('image')
    expect(config.type).toBe('choices')
    expect(config.choice).toBe('multiple')
    expect(config.choices).toEqual([{ value: 'A' }, { value: 'B' }])
  })

  it('toControlConfig 解析 perRegion', () => {
    const xml = `<View>
      <Image name="image" value="$image"/>
      <Rectangle name="box" toName="image"/>
      <TextArea name="label" toName="image" perRegion="true"/>
    </View>`
    const root = parseConfigTree(xml)
    const ta = findFirstNode(root, (n) => n.tag === 'TextArea')!
    const config = toControlConfig(ta)
    expect(config.perRegion).toBe(true)
  })

  it('toControlConfig perRegion 默认 false', () => {
    const xml = `<View>
      <Text name="text" value="$text"/>
      <TextArea name="label" toName="text"/>
    </View>`
    const root = parseConfigTree(xml)
    const ta = findFirstNode(root, (n) => n.tag === 'TextArea')!
    expect(toControlConfig(ta).perRegion).toBeFalsy()
  })

  it('toObjectConfig 生成正确结构', () => {
    const xml = `<View><Image name="img" value="$image"/></View>`
    const root = parseConfigTree(xml)
    const node = findFirstNode(root, (n) => n.tag === 'Image')!
    const obj = toObjectConfig(node)
    expect(obj.tag).toBe('Image')
    expect(obj.name).toBe('img')
    expect(obj.field).toBe('image')
  })
})
