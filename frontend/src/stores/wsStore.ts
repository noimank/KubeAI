import { create } from 'zustand'
import { useAuthStore } from './authStore'
import { useNotificationStore } from './notificationStore'
import { queryClient } from '@/lib/queryClient'
import { buildWsUrl } from '@/utils/constants'

interface WsState {
  connected: boolean
  reconnecting: boolean
  ws: WebSocket | null
  connect: () => void
  disconnect: () => void
}

export const useWsStore = create<WsState>((set, get) => ({
  connected: false,
  reconnecting: false,
  ws: null,

  connect: () => {
    const url = buildWsUrl('/ws')
    let retryDelay = 1000
    const maxDelay = 30000

    const connectWs = () => {
      const token = useAuthStore.getState().accessToken
      if (!token) return

      // 鉴权走同源 Cookie (kubeai_access_token), URL 不携带 token
      const ws = new WebSocket(url)

      ws.onopen = () => {
        set({ connected: true, reconnecting: false })
        retryDelay = 1000
      }

      ws.onmessage = (e) => {
        try {
          handleMessage(JSON.parse(e.data))
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        set({ connected: false, reconnecting: true })
        setTimeout(connectWs, retryDelay)
        retryDelay = Math.min(retryDelay * 2, maxDelay)
      }

      ws.onerror = () => {
        ws.close()
      }

      set({ ws })
    }

    connectWs()
  },

  disconnect: () => {
    const ws = get().ws
    if (ws) {
      ws.onclose = null
      ws.close()
      set({ ws: null, connected: false, reconnecting: false })
    }
  },
}))

function handleMessage(data: { event: string; payload: Record<string, unknown> }) {
  const [domain] = data.event.split('.')

  switch (domain) {
    case 'notification':
      useNotificationStore.getState().handleWsNotification(data.payload)
      break
    case 'training':
      queryClient.invalidateQueries({ queryKey: ['trainingJobs'] })
      if (data.payload.id) {
        queryClient.invalidateQueries({ queryKey: ['trainingJob', data.payload.id as string] })
      }
      break
    case 'inference':
      queryClient.invalidateQueries({ queryKey: ['inferenceServices'] })
      if (data.payload.id) {
        queryClient.invalidateQueries({ queryKey: ['inferenceService', data.payload.id as string] })
      }
      break
    case 'dev_environment':
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
      if (data.payload.id) {
        queryClient.invalidateQueries({ queryKey: ['devEnvironment', data.payload.id as string] })
      }
      break
    case 'cluster_resource':
      queryClient.invalidateQueries({ queryKey: ['clusterOverview'] })
      queryClient.invalidateQueries({ queryKey: ['monitoringTenants'] })
      break
  }
}
