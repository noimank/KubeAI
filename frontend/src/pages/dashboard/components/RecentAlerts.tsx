import { Tag, Timeline } from 'antd'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import type { RecentAlert } from '@/types/dashboard'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const TYPE_CONFIG: Record<string, { color: string; text: string }> = {
  training_job: { color: 'blue', text: '训练任务' },
  quota_alert: { color: 'red', text: '配额告警' },
  annotation_task: { color: 'purple', text: '标注任务' },
  inference_service: { color: 'orange', text: '推理服务' },
}

const PRIORITY_COLOR: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'blue',
}

interface Props {
  data: RecentAlert[]
  loading: boolean
}

export default function RecentAlerts({ data }: Props) {
  return (
    <Timeline
      items={data.map((alert) => {
        const typeCfg = TYPE_CONFIG[alert.type] || { color: 'default', text: alert.type }
        return {
          color: PRIORITY_COLOR[alert.priority] || 'blue',
          children: (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Tag color={typeCfg.color} style={{ margin: 0 }}>
                  {typeCfg.text}
                </Tag>
                <span style={{ fontWeight: 500 }}>{alert.title}</span>
              </div>
              <div style={{ fontSize: 12, color: 'rgba(0,0,0,0.45)', marginTop: 4 }}>
                {dayjs(alert.createdAt).fromNow()}
              </div>
            </div>
          ),
        }
      })}
    />
  )
}
