import type { MessageInstance } from 'antd/es/message/interface'

let messageApi: MessageInstance | null = null

export function setMessageInstance(instance: MessageInstance) {
  messageApi = instance
}

export function getMessageInstance(): MessageInstance | null {
  return messageApi
}
