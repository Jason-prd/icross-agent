import { create } from 'zustand'
import {
  getSessions,
  getSessionMessages,
  deleteSession,
  updateSessionTitle,
  type Session,
  type Message,
  type ToolCall,
} from '../api/sessions'
import { connectChat } from '../api/chat'

interface ToolCallState {
  name: string
  input?: unknown
  output?: unknown
  status: 'running' | 'completed' | 'error'
  id: string // unique per tool call within a response
}

interface ConfirmInfo {
  tool: string
  description: string
  question: string
  input?: unknown
}

interface ChatState {
  sessions: Session[]
  currentSessionId: string | null
  messages: Message[]
  isStreaming: boolean
  currentStreamContent: string
  currentThinking: string
  currentToolCalls: ToolCallState[]
  connected: boolean
  ws: WebSocket | null
  confirmInfo: ConfirmInfo | null  // pending human confirm
  messagesLoading: boolean

  selectedShopIds: string[]
  wsStatus: 'connected' | 'disconnected' | 'connecting'
  setSelectedShopIds: (ids: string[]) => void
  loadSessions: (shopId?: string) => Promise<void>
  selectSession: (id: string) => Promise<void>
  newSession: () => void
  sendMessage: (text: string, shopId: string) => void
  stopStreaming: () => void
  confirmAction: (approved: boolean) => void  // respond to confirm_required
  deleteSessionItem: (id: string) => Promise<void>
  renameSession: (id: string, title: string) => Promise<void>
  clearMessages: () => void
}

let toolCallSeq = 0

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  isStreaming: false,
  currentStreamContent: '',
  currentThinking: '',
  currentToolCalls: [],
  selectedShopIds: [],
  wsStatus: 'disconnected',
  connected: false,
  ws: null,
  confirmInfo: null,
  messagesLoading: false,

  loadSessions: async (shopId?: string) => {
    try {
      const sessions = await getSessions(shopId)
      set({ sessions })
    } catch (err) {
      console.error('Failed to load sessions:', err)
    }
  },

  selectSession: async (id: string) => {
    const { ws } = get()
    if (ws) ws.close()
    set({
      currentSessionId: id,
      messages: [],
      currentStreamContent: '',
      currentThinking: '',
      currentToolCalls: [],
      isStreaming: false,
      ws: null,
      connected: false,
      wsStatus: 'disconnected',
      confirmInfo: null,
      messagesLoading: true,
    })
    try {
      const messages = await getSessionMessages(id)
      set({ messages, messagesLoading: false })
    } catch (err) {
      console.error('Failed to load messages:', err)
      set({ messagesLoading: false })
    }
  },

  newSession: () => {
    const { ws } = get()
    if (ws) ws.close()
    const newId = crypto.randomUUID()
    const newSession: Session = {
      id: newId,
      title: '新会话',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      message_count: 0,
    }
    set({
      currentSessionId: newId,
      messages: [],
      currentStreamContent: '',
      currentThinking: '',
      currentToolCalls: [],
      isStreaming: false,
      ws: null,
      connected: false,
      wsStatus: 'disconnected',
      confirmInfo: null,
      sessions: [newSession, ...get().sessions],
    })
  },

  setSelectedShopIds: (ids: string[]) => set({ selectedShopIds: ids }),

  sendMessage: (text: string, shopId: string) => {
    let { currentSessionId, ws: existingWs, messages, selectedShopIds } = get()

    if (!currentSessionId) {
      currentSessionId = crypto.randomUUID()
      set({ currentSessionId })
    }

    if (existingWs) existingWs.close()
    toolCallSeq = 0

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'human',
      content: text,
      created_at: new Date().toISOString(),
    }
    set({
      messages: [...messages, userMsg],
      isStreaming: true,
      currentStreamContent: '',
      currentThinking: '',
      currentToolCalls: [],
    })

    // Determine effective shop IDs: multi-selection takes priority, else fallback to shopId param
    const shopIds = selectedShopIds.length > 0 ? selectedShopIds : (shopId ? [shopId] : [])
    const primaryShopId = shopIds[0] || shopId || ''

    const ws = connectChat(currentSessionId, primaryShopId)

    set({ wsStatus: 'connecting' })

    ws.onopen = () => {
      set({ connected: true, wsStatus: 'connected', ws })
      const payload: Record<string, unknown> = { content: text }
      if (shopIds.length > 1) {
        payload.shop_ids = shopIds
        payload.shop_id = primaryShopId
      } else if (shopIds.length === 1) {
        payload.shop_id = shopIds[0]
      }
      ws.send(JSON.stringify(payload))
      // Refresh session list so newly created sessions appear
      get().loadSessions(primaryShopId)
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data)
        const state = get()

        switch (data.type) {
          case 'thinking_token': {
            set({ currentThinking: state.currentThinking + (data.content || '') })
            break
          }

          case 'token': {
            set({ currentStreamContent: state.currentStreamContent + (data.content || '') })
            break
          }

          case 'round_end': {
            // Clear thinking between rounds to prevent stale content mixing
            set({ currentThinking: '', currentStreamContent: '' })
            break
          }

          // Backend sends tool_call (not tool_start/tool_end)
          case 'tool_call': {
            if (data.status === 'running') {
              toolCallSeq++
              const tc: ToolCallState = {
                id: `tc-${toolCallSeq}`,
                name: data.name || 'unknown',
                status: 'running',
              }
              set({ currentToolCalls: [...state.currentToolCalls, tc] })
            } else if (data.status === 'completed') {
              const calls = [...state.currentToolCalls]
              // Update the last running tool call with the matching name
              const idx = calls.length - 1
              if (idx >= 0 && calls[idx].name === data.name) {
                calls[idx] = { ...calls[idx], status: 'completed' }
              }
              set({ currentToolCalls: calls })
            }
            break
          }

          case 'message_end': {
            const finalContent = state.currentStreamContent || ''
            const toolCalls: ToolCall[] = state.currentToolCalls.map((tc) => ({
              name: tc.name,
              status: tc.status,
            }))

            const aiMsg: Message = {
              id: crypto.randomUUID(),
              role: 'ai',
              content: finalContent || '(空响应)',
              thinking: state.currentThinking || undefined,
              toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
              created_at: new Date().toISOString(),
            }

            set({
              messages: [...state.messages, aiMsg],
              currentStreamContent: '',
              currentThinking: '',
              currentToolCalls: [],
              isStreaming: false,
            })
            break
          }

          case 'confirm_required': {
            set({
              confirmInfo: {
                tool: data.tool || '',
                description: data.description || '',
                question: data.question || `确认执行: ${data.description}？`,
                input: data.input || undefined,
              },
            })
            break
          }

          case 'error': {
            const errMsg: Message = {
              id: crypto.randomUUID(),
              role: 'ai',
              content: `错误: ${data.message || '未知错误'}`,
              created_at: new Date().toISOString(),
            }
            set({
              messages: [...state.messages, errMsg],
              currentStreamContent: '',
              currentThinking: '',
              currentToolCalls: [],
              isStreaming: false,
              confirmInfo: null,
            })
            break
          }
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err)
      }
    }

    ws.onclose = () => {
      const state = get()
      set({ connected: false, ws: null, wsStatus: 'disconnected' })
      if (state.isStreaming) {
        // Finalize any remaining content
        if (state.currentStreamContent) {
          const toolCalls: ToolCall[] = state.currentToolCalls.map((tc) => ({
            name: tc.name,
            status: tc.status,
          }))
          const finalMsg: Message = {
            id: crypto.randomUUID(),
            role: 'ai',
            content: state.currentStreamContent,
            thinking: state.currentThinking || undefined,
            toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
            created_at: new Date().toISOString(),
          }
          set({
            messages: [...state.messages, finalMsg],
            currentStreamContent: '',
            currentThinking: '',
            currentToolCalls: [],
            isStreaming: false,
          })
        } else {
          set({ isStreaming: false, currentThinking: '', currentToolCalls: [] })
        }
      }
    }

    ws.onerror = () => {
      const state = get()
      const errMsg: Message = {
        id: crypto.randomUUID(),
        role: 'ai',
        content: '连接失败，请检查网络或后端服务是否运行。',
        created_at: new Date().toISOString(),
      }
      set({
        messages: [...state.messages, errMsg],
        currentStreamContent: '',
        currentThinking: '',
        currentToolCalls: [],
        isStreaming: false,
        connected: false,
        wsStatus: 'disconnected',
      })
    }
  },

  stopStreaming: () => {
    const { ws, isStreaming, currentStreamContent, currentThinking, currentToolCalls, messages } = get()
    if (ws) ws.close()
    if (isStreaming && currentStreamContent) {
      const toolCalls: ToolCall[] = currentToolCalls.map((tc) => ({
        name: tc.name,
        status: tc.status,
      }))
      const finalMsg: Message = {
        id: crypto.randomUUID(),
        role: 'ai',
        content: currentStreamContent,
        thinking: currentThinking || undefined,
        toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
        created_at: new Date().toISOString(),
      }
      set({
        messages: [...messages, finalMsg],
        currentStreamContent: '',
        currentThinking: '',
        currentToolCalls: [],
        isStreaming: false,
      })
    }
    set({ ws: null, connected: false, isStreaming: false, confirmInfo: null })
  },

  deleteSessionItem: async (id: string) => {
    try {
      await deleteSession(id)
      const { sessions, currentSessionId } = get()
      set({ sessions: sessions.filter((s) => s.id !== id) })
      if (currentSessionId === id) {
        set({
          currentSessionId: null,
          messages: [],
          currentStreamContent: '',
          currentThinking: '',
          currentToolCalls: [],
          isStreaming: false,
        })
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  },

  renameSession: async (id: string, title: string) => {
    try {
      await updateSessionTitle(id, title)
      const { sessions } = get()
      set({
        sessions: sessions.map((s) =>
          s.id === id ? { ...s, title } : s,
        ),
      })
    } catch (err) {
      console.error('Failed to rename session:', err)
    }
  },

  clearMessages: () => {
    set({ messages: [], currentStreamContent: '', currentThinking: '', currentToolCalls: [], confirmInfo: null })
  },

  confirmAction: (approved: boolean) => {
    const { ws, confirmInfo } = get()
    if (!ws || !confirmInfo) return
    const action = approved ? 'confirm' : 'reject'
    ws.send(JSON.stringify({ action, content: '' }))
    set({ confirmInfo: null })
  },
}))
