import { List, Typography } from 'antd'
import { Link } from 'react-router-dom'
import { DatabaseOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import type { RecentDataset } from '@/types/dashboard'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

interface Props {
  data: RecentDataset[]
  loading: boolean
}

export default function RecentDatasets({ data, loading }: Props) {
  return (
    <List<RecentDataset>
      loading={loading}
      dataSource={data}
      renderItem={(item) => (
        <List.Item style={{ padding: '8px 0' }}>
          <List.Item.Meta
            avatar={<DatabaseOutlined style={{ fontSize: 20, color: '#1677ff', marginTop: 4 }} />}
            title={<Link to={`/datasets/${item.id}`}>{item.displayName || item.name}</Link>}
            description={`${item.versionCount} 个版本 · ${item.fileCount} 个文件 · ${dayjs(item.updatedAt).fromNow()}`}
          />
        </List.Item>
      )}
      footer={
        <Typography.Link>
          <Link to="/datasets">查看全部</Link>
        </Typography.Link>
      }
    />
  )
}
