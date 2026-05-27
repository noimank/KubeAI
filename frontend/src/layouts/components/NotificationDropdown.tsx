import { useState, useCallback } from 'react'
import type { CSSProperties } from 'react'
import {
  Badge,
  Dropdown,
  List,
  Tag,
  Button,
  Segmented,
  Empty,
  Spin,
  App,
  theme,
  ConfigProvider,
  Typography,
} from 'antd'
import { BellOutlined, CheckOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

import { getNotifications, markAsRead, markAllAsRead } from '@/services/notifications'
import { useNotificationStore } from '@/stores/notificationStore'
import { useThemeStore } from '@/stores/themeStore'
import type { Notification, NotificationType } from '@/types/notification'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const TYPE_CONFIG: Record<NotificationType, { color: string; text: string }> = {
  training_job: { color: 'blue', text: '训练任务' },
  quota_alert: { color: 'red', text: '配额告警' },
  annotation_task: { color: 'purple', text: '标注任务' },
  inference_service: { color: 'orange', text: '推理服务' },
}

const FILTER_OPTIONS = [
  { label: '全部', value: '' },
  { label: '训练', value: 'training_job' },
  { label: '配额', value: 'quota_alert' },
  { label: '标注', value: 'annotation_task' },
  { label: '推理', value: 'inference_service' },
]

/* ── Panel content (rendered inside theme-correct ConfigProvider) ── */

interface PanelProps {
  unreadCount: number
  filter: string
  onFilterChange: (v: string) => void
  isLoading: boolean
  notifications: Notification[]
  onItemClick: (item: Notification) => void
  onMarkAllRead: () => void
  markAllPending: boolean
  onViewAll: () => void
}

function NotificationPanelContent({
  unreadCount,
  filter,
  onFilterChange,
  isLoading,
  notifications,
  onItemClick,
  onMarkAllRead,
  markAllPending,
  onViewAll,
}: PanelProps) {
  const { token } = theme.useToken()
  const isDark = useThemeStore((s) => s.themeMode) === 'dark'

  const panelStyle: CSSProperties = {
    '--notification-item-hover-bg': token.colorFillSecondary,
    '--notification-scroll-thumb': isDark ? token.colorFillSecondary : token.colorFill,
    width: 400,
    maxWidth: 'calc(100vw - 32px)',
    maxHeight: 'min(520px, calc(100vh - 96px))',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    color: token.colorText,
    background: token.colorBgElevated,
    border: `1px solid ${token.colorBorderSecondary}`,
    borderRadius: token.borderRadiusLG,
    boxShadow: isDark
      ? '0 16px 40px rgba(0,0,0,.56), 0 0 0 1px rgba(255,255,255,.04)'
      : '0 16px 40px rgba(15,23,42,.14), 0 2px 8px rgba(15,23,42,.08)',
  } as CSSProperties

  const headerStyle: CSSProperties = {
    padding: '14px 16px 12px',
    background: token.colorFillAlter,
    borderBottom: `1px solid ${token.colorSplit}`,
  }

  const filterStyle: CSSProperties = {
    '--notification-filter-thumb-bg': token.colorBgContainer,
    width: '100%',
    background: token.colorBgLayout,
  } as CSSProperties

  const listItemStyle = (isRead: boolean): CSSProperties => ({
    padding: '12px 16px',
    cursor: 'pointer',
    background: isRead ? token.colorBgContainer : token.colorPrimaryBg,
    borderLeft: `3px solid ${isRead ? 'transparent' : token.colorPrimaryBorder}`,
    borderBottom: `1px solid ${token.colorSplit}`,
    transition: 'background-color 0.2s ease',
  })

  return (
    <div className="notification-dropdown-panel" style={panelStyle}>
      <div style={headerStyle}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <span style={{ fontWeight: 600, fontSize: 15, lineHeight: '22px' }}>通知</span>
            {unreadCount > 0 && (
              <span
                style={{
                  flexShrink: 0,
                  color: token.colorTextSecondary,
                  fontSize: 12,
                  lineHeight: '20px',
                }}
              >
                {unreadCount} 条未读
              </span>
            )}
          </div>
          {unreadCount > 0 ? (
            <Button
              type="link"
              size="small"
              icon={<CheckOutlined />}
              onClick={onMarkAllRead}
              loading={markAllPending}
              style={{ paddingInline: 0, flexShrink: 0 }}
            >
              全部已读
            </Button>
          ) : null}
        </div>
        <Segmented
          options={FILTER_OPTIONS}
          value={filter}
          onChange={(v) => onFilterChange(v as string)}
          size="small"
          block
          className="notification-dropdown-filter"
          style={filterStyle}
        />
      </div>
      <div
        className="notification-dropdown-body"
        style={{
          flex: 1,
          minHeight: 180,
          overflowY: 'auto',
          background: token.colorBgContainer,
        }}
      >
        {isLoading ? (
          <div style={{ display: 'grid', minHeight: 180, placeItems: 'center' }}>
            <Spin />
          </div>
        ) : notifications.length === 0 ? (
          <div style={{ display: 'grid', minHeight: 180, placeItems: 'center', padding: 24 }}>
            <Empty description="暂无通知" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          </div>
        ) : (
          <List
            split={false}
            dataSource={notifications}
            renderItem={(item: Notification) => {
              const cfg = TYPE_CONFIG[item.type]
              return (
                <List.Item
                  className="notification-dropdown-item"
                  style={listItemStyle(item.isRead)}
                  onClick={() => onItemClick(item)}
                >
                  <List.Item.Meta
                    title={
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                        <Tag color={cfg.color} style={{ margin: 0, fontSize: 11 }}>
                          {cfg.text}
                        </Tag>
                        <span
                          className="notification-dropdown-title"
                          style={{
                            flex: 1,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontWeight: item.isRead ? 400 : 600,
                            color: token.colorText,
                          }}
                        >
                          {item.title}
                        </span>
                        {!item.isRead && (
                          <span
                            style={{
                              width: 6,
                              height: 6,
                              borderRadius: '50%',
                              background: token.colorPrimary,
                              flexShrink: 0,
                            }}
                          />
                        )}
                      </div>
                    }
                    description={
                      <div>
                        <div
                          className="notification-dropdown-content"
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontSize: 12,
                            color: token.colorTextSecondary,
                            lineHeight: '20px',
                          }}
                        >
                          {item.content}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: token.colorTextTertiary,
                            marginTop: 4,
                            lineHeight: '18px',
                          }}
                        >
                          {dayjs(item.createdAt).fromNow()}
                        </div>
                      </div>
                    }
                  />
                </List.Item>
              )
            }}
          />
        )}
      </div>
      <div
        style={{
          padding: '8px 16px',
          borderTop: `1px solid ${token.colorSplit}`,
          textAlign: 'center',
        }}
      >
        <Typography.Link onClick={onViewAll}>查看全部通知</Typography.Link>
      </div>
    </div>
  )
}

/* ── Main dropdown trigger ── */

interface NotificationDropdownProps {
  unreadCount: number
}

export function NotificationDropdown({ unreadCount }: NotificationDropdownProps) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const themeMode = useThemeStore((s) => s.themeMode)
  const isDark = themeMode === 'dark'
  const clearUnread = useNotificationStore((s) => s.clearUnread)
  const decrementUnread = useNotificationStore((s) => s.decrementUnread)
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', filter],
    queryFn: () =>
      getNotifications({
        current: 1,
        pageSize: 10,
        type: (filter || undefined) as NotificationType | undefined,
      }),
    enabled: open,
  })

  const readMutation = useMutation({
    mutationFn: markAsRead,
    onSuccess: () => {
      decrementUnread()
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const readAllMutation = useMutation({
    mutationFn: markAllAsRead,
    onSuccess: () => {
      clearUnread()
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      message.success('已全部标记为已读')
    },
  })

  const handleItemClick = useCallback(
    (item: Notification) => {
      if (!item.isRead) {
        readMutation.mutate(item.id)
      }
      if (item.resourceType && item.resourceId) {
        const routeMap: Record<string, string> = {
          training_job: `/training-jobs/${item.resourceId}`,
          inference_service: `/inference/${item.resourceId}`,
          annotation_project: `/annotations/${item.resourceId}`,
          dataset: `/datasets/${item.resourceId}`,
        }
        const route = routeMap[item.resourceType]
        if (route) {
          setOpen(false)
          navigate(route)
        }
      }
    },
    [readMutation, navigate],
  )

  const handleViewAll = useCallback(() => {
    setOpen(false)
    navigate('/notifications')
  }, [navigate])

  const notifications = data?.data?.items ?? []

  return (
    <div className="notification-dropdown-shell">
      <Dropdown
        popupRender={() => (
          <ConfigProvider
            theme={{ algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }}
          >
            <NotificationPanelContent
              unreadCount={unreadCount}
              filter={filter}
              onFilterChange={setFilter}
              isLoading={isLoading}
              notifications={notifications}
              onItemClick={handleItemClick}
              onMarkAllRead={() => readAllMutation.mutate()}
              markAllPending={readAllMutation.isPending}
              onViewAll={handleViewAll}
            />
          </ConfigProvider>
        )}
        trigger={['click']}
        open={open}
        onOpenChange={setOpen}
        placement="bottomRight"
        overlayStyle={{ paddingTop: 8 }}
      >
        <button
          type="button"
          aria-label="通知"
          title="通知"
          className="notification-trigger-button"
        >
          <Badge count={unreadCount} showZero={false} styles={{ root: { display: 'inline-flex' } }}>
            <BellOutlined style={{ fontSize: 16 }} />
          </Badge>
        </button>
      </Dropdown>
    </div>
  )
}
