import client from './client'

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count?: number
}

export interface ToolCall {
  name: string
  input?: unknown
  output?: unknown
  status: 'running' | 'completed' | 'error'
}

export interface Message {
  id: string
  role: 'human' | 'ai' | 'tool'
  content: string
  thinking?: string          // Extracted thinking content (for AI messages)
  tool_name?: string
  tool_input?: unknown
  tool_output?: unknown
  toolCalls?: ToolCall[]     // Grouped tool calls (for AI messages from loaded history)
  created_at: string
}

export async function getSessions(shopId?: string): Promise<Session[]> {
  const params = shopId ? { shop_id: shopId } : {}
  const res = await client.get('/api/sessions', { params })
  return (res.data.sessions ?? []).map((s: Record<string, unknown>) => ({
    id: (s.session_id ?? s.id) as string,
    title: (s.title ?? '新会话') as string,
    created_at: s.created_at as string,
    updated_at: s.updated_at as string,
    message_count: (s.message_count as number) ?? 0,
  }))
}

/**
 * Parse a raw message content from the backend into { thinking, text }.
 * MiniMax returns content as a list of blocks: [{type:"thinking",...}, {type:"text",...}]
 */
function parseContentBlocks(content: unknown): { thinking: string; text: string } {
  if (Array.isArray(content)) {
    let thinking = ''
    let text = ''
    for (const block of content) {
      if (typeof block === 'object' && block !== null) {
        const b = block as Record<string, unknown>
        if (b.type === 'thinking') thinking = (b.thinking ?? '') as string
        else if (b.type === 'text') text = (b.text ?? '') as string
      }
    }
    return { thinking, text }
  }
  if (typeof content === 'string') return { thinking: '', text: content }
  return { thinking: '', text: String(content ?? '') }
}

export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  const res = await client.get(`/api/sessions/${sessionId}/messages`)
  const rawMessages: Record<string, unknown>[] = res.data.messages ?? []

  // Step 1: parse raw messages into Message[]
  const parsed: Message[] = rawMessages.map((m) => {
    const rawRole = (m.message_type ?? m.type ?? m.role ?? 'unknown') as string
    const rawContent = m.content ?? ''
    let content = ''
    let thinking: string | undefined

    if (rawRole === 'ai') {
      const parsed = parseContentBlocks(rawContent)
      thinking = parsed.thinking || undefined
      content = parsed.text
    } else {
      content = Array.isArray(rawContent)
        ? JSON.stringify(rawContent)
        : String(rawContent)
    }

    return {
      id: (m.message_id ?? m.id ?? crypto.randomUUID()) as string,
      role: rawRole === 'human' ? 'human' : rawRole === 'ai' ? 'ai' : 'tool',
      content,
      thinking,
      tool_name: m.tool_name as string | undefined,
      tool_input: m.tool_input as unknown,
      tool_output: m.tool_output as unknown,
      created_at: (m.created_at as string) ?? new Date().toISOString(),
    }
  })

  // Step 2: group tool_result messages into preceding AI messages
  const grouped: Message[] = []
  let currentAi: Message | null = null

  for (const msg of parsed) {
    if (msg.role === 'ai') {
      if (currentAi) grouped.push(currentAi)
      currentAi = { ...msg, toolCalls: [] }
    } else if (msg.role === 'tool' && currentAi) {
      // Collect tool result into current AI message's toolCalls
      currentAi.toolCalls!.push({
        name: msg.tool_name || 'unknown',
        input: msg.tool_input,
        output: msg.tool_output,
        status: 'completed',
      })
    } else {
      if (currentAi) { grouped.push(currentAi); currentAi = null }
      grouped.push(msg)
    }
  }
  if (currentAi) grouped.push(currentAi)

  // Clean up empty toolCalls arrays (AI messages without tool calls)
  for (const msg of grouped) {
    if (msg.role === 'ai' && msg.toolCalls?.length === 0) {
      delete msg.toolCalls
    }
  }

  return grouped
}

export async function deleteSession(sessionId: string): Promise<void> {
  await client.delete(`/api/sessions/${sessionId}`)
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<void> {
  await client.patch(`/api/sessions/${sessionId}`, { title })
}
