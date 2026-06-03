export type WsMessageType = 'tool_start' | 'token' | 'thinking_token' | 'message' | 'message_end' | 'tool_end' | 'error'

export interface WsMessage {
  type: WsMessageType
  content?: string
  role?: 'ai' | 'human' | 'tool'
  tool?: string
  input?: unknown
  output?: unknown
  message?: string
}

export function connectChat(sessionId: string, shopId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/api/chat?session_id=${encodeURIComponent(sessionId)}&shop_id=${encodeURIComponent(shopId)}`
  return new WebSocket(url)
}
