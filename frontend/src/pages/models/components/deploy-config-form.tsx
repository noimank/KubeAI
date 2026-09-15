import { forwardRef, useImperativeHandle } from 'react'
import { Collapse, Form, Input, InputNumber, Radio, Select } from 'antd'
import ImageSelect from '@/components/ImageSelect'
import EnvVarEditor from '@/components/EnvVarEditor'
import type { ModelDeployConfig, ModelDeployConfigInput } from '@/types/model'

const MEMORY_OPTIONS = [
  { label: '4 Gi', value: '4Gi' },
  { label: '8 Gi', value: '8Gi' },
  { label: '16 Gi', value: '16Gi' },
  { label: '32 Gi', value: '32Gi' },
  { label: '64 Gi', value: '64Gi' },
]

interface DeployConfigFormValues {
  imageIds?: string[]
  containerPort?: number | null
  subpathMode?: 'rewrite' | 'native' | null
  command?: string
  args?: string
  envVars?: { key?: string; value?: string }[]
  gpuCount?: number | null
  cpu?: number | null
  memory?: string
  replicas?: number | null
}

export interface DeployConfigFormRef {
  /** 校验并返回提交用部署配置; 全部留空返回 undefined (不保存配置) */
  getSubmitConfig: () => Promise<ModelDeployConfigInput | undefined>
}

interface DeployConfigFormProps {
  /** 预填的部署配置 (如上一版本沉淀的配置) */
  initialConfig?: ModelDeployConfig | null
}

/** 「推理部署配置」表单 — 上传模型与编辑版本部署配置共用 */
const DeployConfigForm = forwardRef<DeployConfigFormRef, DeployConfigFormProps>(
  function DeployConfigForm({ initialConfig }, ref) {
    const [form] = Form.useForm<DeployConfigFormValues>()

    const initialValues: DeployConfigFormValues | undefined = initialConfig
      ? {
          imageIds: initialConfig.images?.map((i) => i.imageId),
          containerPort: initialConfig.containerPort ?? undefined,
          subpathMode: initialConfig.subpathMode ?? undefined,
          command: initialConfig.command?.join(' '),
          args: initialConfig.args?.join(' '),
          envVars: initialConfig.envVars
            ? Object.entries(initialConfig.envVars).map(([key, value]) => ({ key, value }))
            : undefined,
          gpuCount: initialConfig.gpuCount ?? undefined,
          cpu: initialConfig.cpu ? Number(initialConfig.cpu) : undefined,
          memory: initialConfig.memory ?? undefined,
          replicas: initialConfig.replicas ?? undefined,
        }
      : undefined

    useImperativeHandle(ref, () => ({
      getSubmitConfig: async () => {
        const values = await form.validateFields()
        const envVars = values.envVars?.reduce((acc: Record<string, string>, item) => {
          const key = item.key?.trim()
          if (key) acc[key] = item.value ?? ''
          return acc
        }, {})
        const config: ModelDeployConfigInput = {
          imageIds: values.imageIds ?? [],
          containerPort: values.containerPort ?? undefined,
          subpathMode: values.subpathMode ?? undefined,
          command: values.command ? values.command.split(/\s+/).filter(Boolean) : undefined,
          args: values.args ? values.args.split(/\s+/).filter(Boolean) : undefined,
          envVars: envVars && Object.keys(envVars).length > 0 ? envVars : undefined,
          gpuCount: values.gpuCount ?? undefined,
          cpu: values.cpu != null ? String(values.cpu) : undefined,
          memory: values.memory ?? undefined,
          replicas: values.replicas ?? undefined,
        }
        const hasAny =
          (config.imageIds?.length ?? 0) > 0 ||
          config.containerPort != null ||
          config.subpathMode != null ||
          (config.command?.length ?? 0) > 0 ||
          (config.args?.length ?? 0) > 0 ||
          Object.keys(config.envVars ?? {}).length > 0 ||
          config.gpuCount != null ||
          config.cpu != null ||
          config.memory != null ||
          config.replicas != null
        return hasAny ? config : undefined
      },
    }))

    return (
      <Collapse
        size="small"
        defaultActiveKey={initialConfig ? 'deploy-config' : undefined}
        items={[
          {
            key: 'deploy-config',
            label: '推理部署配置（可选 — 部署为推理服务时自动填充）',
            children: (
              <Form<DeployConfigFormValues>
                form={form}
                layout="vertical"
                initialValues={initialValues}
                style={{ marginTop: 4 }}
              >
                <Form.Item
                  name="imageIds"
                  label="候选推理镜像"
                  extra="有序候选，部署时默认使用第一个；部署时仍可自由切换其它推理镜像"
                >
                  <ImageSelect
                    placeholder="选择候选推理镜像（可多选）"
                    category="inference"
                    multiple
                  />
                </Form.Item>
                <div style={{ display: 'flex', gap: 16 }}>
                  <Form.Item
                    name="containerPort"
                    label="容器端口"
                    rules={[{ type: 'number', min: 1, max: 65535, message: '端口范围为 1-65535' }]}
                    style={{ flex: 1 }}
                  >
                    <InputNumber
                      min={1}
                      max={65535}
                      style={{ width: '100%' }}
                      placeholder="如 8080"
                    />
                  </Form.Item>
                  <Form.Item
                    name="subpathMode"
                    label="子路径模式"
                    tooltip="应用是否自行处理 /inference/<hex> 访问前缀；留空则部署时默认「重写」"
                    style={{ flex: 1 }}
                  >
                    <Radio.Group>
                      <Radio value="rewrite">重写（剥前缀）</Radio>
                      <Radio value="native">透传（保留前缀）</Radio>
                    </Radio.Group>
                  </Form.Item>
                </div>
                <Form.Item
                  name="command"
                  label="启动命令"
                  extra="覆盖镜像默认 ENTRYPOINT，如 python main.py（空格分隔）"
                >
                  <Input placeholder="如 python main.py" />
                </Form.Item>
                <Form.Item name="args" label="启动参数" extra="空格分隔，追加到命令之后">
                  <Input placeholder="如 --host 0.0.0.0 --port 8080" />
                </Form.Item>
                <Form.Item label="环境变量">
                  <EnvVarEditor />
                </Form.Item>
                <Form.Item label="资源建议（可选）" style={{ marginBottom: 0 }}>
                  <div style={{ display: 'flex', gap: 16 }}>
                    <Form.Item name="gpuCount" style={{ flex: 1, marginBottom: 0 }}>
                      <InputNumber
                        min={0}
                        max={16}
                        style={{ width: '100%' }}
                        placeholder="GPU 数量"
                      />
                    </Form.Item>
                    <Form.Item name="cpu" style={{ flex: 1, marginBottom: 0 }}>
                      <InputNumber
                        min={1}
                        max={128}
                        style={{ width: '100%' }}
                        placeholder="CPU（核）"
                      />
                    </Form.Item>
                    <Form.Item name="memory" style={{ flex: 1, marginBottom: 0 }}>
                      <Select options={MEMORY_OPTIONS} placeholder="内存" allowClear />
                    </Form.Item>
                    <Form.Item name="replicas" style={{ flex: 1, marginBottom: 0 }}>
                      <InputNumber
                        min={1}
                        max={10}
                        style={{ width: '100%' }}
                        placeholder="副本数"
                      />
                    </Form.Item>
                  </div>
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />
    )
  },
)

export default DeployConfigForm
