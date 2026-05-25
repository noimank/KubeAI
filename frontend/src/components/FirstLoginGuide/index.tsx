import { useEffect, useState } from 'react'
import { Tour } from 'antd'
import type { TourProps } from 'antd'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'

const GUIDE_STEPS: Record<string, TourProps['steps']> = {
  admin: [
    {
      title: '欢迎使用 KubeAI',
      description: '这是您的管理员工作台，可以查看集群资源概览、租户使用排行和最近告警通知。',
      target: null,
    },
    {
      title: '侧边栏导航',
      description: '通过左侧菜单访问平台的各个功能模块，包括租户管理、用户管理和监控等功能。',
      target: () => document.querySelector('.ant-pro-sider') as HTMLElement,
      placement: 'right',
    },
    {
      title: '通知中心',
      description: '点击顶栏铃铛图标查看平台通知，包括配额告警、任务状态变更等重要消息。',
      target: () => document.querySelector('.notification-trigger-button') as HTMLElement,
      placement: 'bottomRight',
    },
    {
      title: '监控仪表盘',
      description: '在「监控」页面可以查看详细的集群资源使用情况、配额分配和资源清理。',
      target: null,
    },
  ],
  engineer: [
    {
      title: '欢迎使用 KubeAI',
      description: '这是您的工程师工作台，可以查看最近的训练任务、数据集和资源概览。',
      target: null,
    },
    {
      title: '训练任务',
      description: '在「训练任务」中创建和管理 GPU 训练任务，支持日志查看和 GPU 监控。',
      target: () => {
        const items = document.querySelectorAll('.ant-menu-item')
        for (const item of items) {
          if (item.textContent?.includes('训练任务')) return item as HTMLElement
        }
        return document.body
      },
      placement: 'right',
    },
    {
      title: '数据集管理',
      description: '在「数据集」中上传和管理训练数据，支持多版本管理和在线预览。',
      target: () => {
        const items = document.querySelectorAll('.ant-menu-item')
        for (const item of items) {
          if (item.textContent?.includes('数据集')) return item as HTMLElement
        }
        return document.body
      },
      placement: 'right',
    },
    {
      title: '模型仓库',
      description: '在「模型仓库」中管理训练产出的模型，支持版本管理和模型注册。',
      target: null,
    },
  ],
  annotator: [
    {
      title: '欢迎使用 KubeAI',
      description: '这是您的标注工作台，可以查看待办任务、进度统计和项目分配。',
      target: null,
    },
    {
      title: '标注任务',
      description: '在「数据标注」中查看分配给您的标注项目，点击即可进入标注工作台。',
      target: () => {
        const items = document.querySelectorAll('.ant-menu-item')
        for (const item of items) {
          if (item.textContent?.includes('数据标注')) return item as HTMLElement
        }
        return document.body
      },
      placement: 'right',
    },
    {
      title: '标注工作台',
      description: '进入项目后可以开始标注工作，系统会自动保存您的标注结果。',
      target: null,
    },
  ],
  mlops: [
    {
      title: '欢迎使用 KubeAI',
      description: '这是您的 MLOps 工台，可以查看推理服务状态和资源概览。',
      target: null,
    },
    {
      title: '推理服务',
      description: '在「推理服务」中部署和管理模型推理服务，支持自动扩缩容和金丝雀发布。',
      target: () => {
        const items = document.querySelectorAll('.ant-menu-item')
        for (const item of items) {
          if (item.textContent?.includes('推理服务')) return item as HTMLElement
        }
        return document.body
      },
      placement: 'right',
    },
    {
      title: '监控',
      description: '在「监控」中查看集群资源使用情况和配额管理。',
      target: () => {
        const items = document.querySelectorAll('.ant-menu-item')
        for (const item of items) {
          if (item.textContent?.includes('监控')) return item as HTMLElement
        }
        return document.body
      },
      placement: 'right',
    },
  ],
}

export default function FirstLoginGuide() {
  const [open, setOpen] = useState(false)
  const role = useRbacStore((s) => s.currentRole)
  const user = useAuthStore((s) => s.user)

  useEffect(() => {
    if (!user || !role) return
    const key = `kubeai_guide_seen_${user.id}`
    const seen = localStorage.getItem(key)
    if (!seen) {
      const timer = setTimeout(() => setOpen(true), 800)
      return () => clearTimeout(timer)
    }
  }, [user, role])

  const handleClose = () => {
    setOpen(false)
    if (user) {
      localStorage.setItem(`kubeai_guide_seen_${user.id}`, 'true')
    }
  }

  if (!role) return null

  const steps = GUIDE_STEPS[role] || GUIDE_STEPS.engineer

  return <Tour open={open} onClose={handleClose} steps={steps} />
}
