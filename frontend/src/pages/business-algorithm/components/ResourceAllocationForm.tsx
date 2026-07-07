import { useState } from 'react'
import { Form, Input, InputNumber, Select, Button, Card, Space, Row, Col } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'

interface Device {
  name: string
  maxCapacity: number | null
  minOperatingLoad: number | null
}

interface ManipulatedObject {
  name: string
  totalAvailable: number | null
  unitCost: number | null
  unitConsumption: number | null
}

export interface ResourceAllocationFormData {
  totalDemand: number | null
  devices: Device[]
  manipulatedObjects: ManipulatedObject[]
  runtimePref: string
}

interface Props {
  algorithmName: string
  onSubmit: (data: Record<string, unknown>) => void
  onCancel: () => void
  loading: boolean
}

export default function ResourceAllocationForm({
  algorithmName,
  onSubmit,
  onCancel,
  loading,
}: Props) {
  const [form] = Form.useForm()
  const [deviceList, setDeviceList] = useState<Device[]>([
    { name: '', maxCapacity: null, minOperatingLoad: null },
  ])
  const [objectList, setObjectList] = useState<ManipulatedObject[]>([
    { name: '', totalAvailable: null, unitCost: null, unitConsumption: null },
  ])

  const handleSubmit = () => {
    form.validateFields().then((values) => {
      onSubmit({
        ...values,
        devices: deviceList,
        manipulatedObjects: objectList,
      })
    })
  }

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <h2 style={{ textAlign: 'center', marginBottom: 40, fontSize: 24, fontWeight: 600 }}>
        {algorithmName}-优化参数
      </h2>
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          totalDemand: null,
          runtimePref: 'speed',
        }}
      >
        <Card style={{ marginBottom: 24 }}>
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              marginBottom: 20,
              paddingBottom: 10,
              borderBottom: '1px solid var(--ant-color-border)',
            }}
          >
            1. 总处理器需求配置
          </h3>
          <Form.Item
            label="总处理器需求(单位)"
            name="totalDemand"
            rules={[{ required: true, message: '请输入总处理器需求' }]}
          >
            <InputNumber style={{ width: '100%' }} placeholder="请输入总处理器需求" min={0} />
          </Form.Item>
          <div style={{ fontSize: 12, color: 'var(--ant-color-text-tertiary)' }}>
            可填写：件、吨、个等，需与后续参数单位一致
          </div>
        </Card>

        <Card style={{ marginBottom: 24 }}>
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              marginBottom: 20,
              paddingBottom: 10,
              borderBottom: '1px solid var(--ant-color-border)',
            }}
          >
            2. 目标对象参数配置
          </h3>
          {deviceList.map((device, index) => (
            <Card
              key={index}
              size="small"
              style={{ marginBottom: 16, background: 'var(--ant-color-fill-tertiary)' }}
              title={<span style={{ fontWeight: 500 }}>目标对象{index + 1}</span>}
              extra={
                index > 0 ? (
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => setDeviceList(deviceList.filter((_, i) => i !== index))}
                  >
                    删除
                  </Button>
                ) : null
              }
            >
              <Row gutter={16}>
                <Col span={8}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    设备名称 {index === 0 ? '*' : ''}
                  </label>
                  <Input
                    value={device.name}
                    placeholder="请输入设备名称"
                    onChange={(e) => {
                      const newList = [...deviceList]
                      newList[index] = { ...newList[index], name: e.target.value }
                      setDeviceList(newList)
                    }}
                  />
                  {index === 0 && !device.name && (
                    <div style={{ color: '#FF4D4F', fontSize: 12, marginTop: 4 }}>
                      请输入设备名称
                    </div>
                  )}
                </Col>
                <Col span={8}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    最大处理能力（单位/天）
                  </label>
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder="请输入"
                    value={device.maxCapacity}
                    onChange={(val) => {
                      const newList = [...deviceList]
                      newList[index] = { ...newList[index], maxCapacity: val }
                      setDeviceList(newList)
                    }}
                  />
                </Col>
                <Col span={8}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    最小操作负荷（单位/天）
                  </label>
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder="请输入"
                    value={device.minOperatingLoad}
                    onChange={(val) => {
                      const newList = [...deviceList]
                      newList[index] = { ...newList[index], minOperatingLoad: val }
                      setDeviceList(newList)
                    }}
                  />
                </Col>
              </Row>
            </Card>
          ))}
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            block
            onClick={() =>
              setDeviceList([
                ...deviceList,
                { name: '', maxCapacity: null, minOperatingLoad: null },
              ])
            }
          >
            添加目标对象
          </Button>
        </Card>

        <Card style={{ marginBottom: 24 }}>
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              marginBottom: 20,
              paddingBottom: 10,
              borderBottom: '1px solid var(--ant-color-border)',
            }}
          >
            3. 优化对象参数配置
          </h3>
          {objectList.map((obj, index) => (
            <Card
              key={index}
              size="small"
              style={{ marginBottom: 16, background: 'var(--ant-color-fill-tertiary)' }}
              title={<span style={{ fontWeight: 500 }}>优化对象{index + 1}</span>}
              extra={
                index > 0 ? (
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => setObjectList(objectList.filter((_, i) => i !== index))}
                  >
                    删除
                  </Button>
                ) : null
              }
            >
              <Row gutter={16}>
                <Col span={6}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    优化对象名称 {index === 0 ? '*' : ''}
                  </label>
                  <Input
                    value={obj.name}
                    placeholder="请输入名称"
                    onChange={(e) => {
                      const newList = [...objectList]
                      newList[index] = { ...newList[index], name: e.target.value }
                      setObjectList(newList)
                    }}
                  />
                </Col>
                <Col span={6}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    可用总量（单位）
                  </label>
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder="请输入"
                    value={obj.totalAvailable}
                    onChange={(val) => {
                      const newList = [...objectList]
                      newList[index] = { ...newList[index], totalAvailable: val }
                      setObjectList(newList)
                    }}
                  />
                </Col>
                <Col span={6}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    单位成本（元/单位）
                  </label>
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder="请输入"
                    value={obj.unitCost}
                    onChange={(val) => {
                      const newList = [...objectList]
                      newList[index] = { ...newList[index], unitCost: val }
                      setObjectList(newList)
                    }}
                  />
                </Col>
                <Col span={6}>
                  <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                    单位消耗（资源/单位对象）
                  </label>
                  <InputNumber
                    style={{ width: '100%' }}
                    placeholder="请输入"
                    value={obj.unitConsumption}
                    onChange={(val) => {
                      const newList = [...objectList]
                      newList[index] = { ...newList[index], unitConsumption: val }
                      setObjectList(newList)
                    }}
                  />
                </Col>
              </Row>
            </Card>
          ))}
          <Button
            type="dashed"
            icon={<PlusOutlined />}
            block
            onClick={() =>
              setObjectList([
                ...objectList,
                { name: '', totalAvailable: null, unitCost: null, unitConsumption: null },
              ])
            }
          >
            添加优化对象
          </Button>
        </Card>

        <Card style={{ marginBottom: 24 }}>
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              marginBottom: 20,
              paddingBottom: 10,
              borderBottom: '1px solid var(--ant-color-border)',
            }}
          >
            4. 优化算法参数配置
          </h3>
          <Form.Item
            label="运行偏好"
            name="runtimePref"
            rules={[{ required: true, message: '请选择运行偏好' }]}
          >
            <Select placeholder="请选择运行偏好">
              <Select.Option value="speed">speed（速度优先）</Select.Option>
              <Select.Option value="balanced">balanced（平衡）</Select.Option>
              <Select.Option value="precision">precision（精度优先）</Select.Option>
            </Select>
          </Form.Item>
        </Card>

        <div style={{ textAlign: 'center', marginTop: 40 }}>
          <Space size="large">
            <Button size="large" disabled={loading} onClick={onCancel}>
              取消
            </Button>
            <Button type="primary" size="large" loading={loading} onClick={handleSubmit}>
              提交优化参数
            </Button>
          </Space>
        </div>
      </Form>
    </div>
  )
}
