import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Input,
  Button,
  Typography,
  Space,
  Collapse,
  Spin,
  Empty,
  Skeleton,
  Modal,
  Alert,
} from 'antd'
import {
  SendOutlined,
  StopOutlined,
  SyncOutlined,
  UploadOutlined,
  RobotOutlined,
  UserOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  CopyOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '../stores/chatStore'
import { useWebSocket } from '../hooks/useWebSocket'
import type { Message, ToolCall } from '../api/sessions'
import dayjs from 'dayjs'

const { Text } = Typography
const { TextArea } = Input

export default function ChatPanel({ shopId }: { shopId: string }) {
  const messages = useChatStore((s) => s.messages)
  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const wsStatus = useChatStore((s) => s.wsStatus)
  const currentStreamContent = useChatStore((s) => s.currentStreamContent)
  const currentThinking = useChatStore((s) => s.currentThinking)
  const currentToolCalls = useChatStore((s) => s.currentToolCalls)
  const confirmInfo = useChatStore((s) => s.confirmInfo)
  const confirmAction = useChatStore((s) => s.confirmAction)
  const messagesLoading = useChatStore((s) => s.messagesLoading)
  const { send, stop } = useWebSocket()

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [inputValue, setInputValue] = useState('')
  const isNearBottom = useRef(true)

  // Smart auto-scroll: only scroll if user is near the bottom
  useEffect(() => {
    const container = messagesContainerRef.current
    if (!container || !isNearBottom.current) return
    messagesEndRef.current?.scrollIntoView({ behavior: 'instant' })
  }, [currentStreamContent, currentThinking, currentToolCalls])

  // Smooth scroll on new messages (non-streaming)
  useEffect(() => {
    if (!isNearBottom.current) return
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Track scroll position
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current
    if (!container) return
    const threshold = 100
    isNearBottom.current =
      container.scrollHeight - container.scrollTop - container.clientHeight < threshold
  }, [])

  const handleSend = () => {
    const text = inputValue.trim()
    if (!text || !currentSessionId) return
    send(text, shopId)
    setInputValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Empty state: no session selected
  if (!currentSessionId) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
        }}
      >
        <Empty description="选择一个会话开始，或输入你的经营目标" />
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '16px 24px',
        }}
      >
        {/* Loading skeleton */}
        {messagesLoading && (
          <div style={{ padding: '0 16px' }}>
            <Skeleton active avatar={{ shape: 'circle', size: 32 }} paragraph={{ rows: 2 }} />
            <div style={{ marginTop: 24 }}>
              <Skeleton active avatar={{ shape: 'circle', size: 32 }} paragraph={{ rows: 1 }} style={{ display: 'flex', flexDirection: 'row-reverse' }} />
            </div>
            <div style={{ marginTop: 24 }}>
              <Skeleton active avatar={{ shape: 'circle', size: 32 }} paragraph={{ rows: 3 }} />
            </div>
          </div>
        )}

        {/* Empty state: new session, no messages yet */}
        {messages.length === 0 && !isStreaming && !messagesLoading && (
          <div
            style={{
              textAlign: 'center',
              paddingTop: 80,
              color: '#bbb',
            }}
          >
            <RobotOutlined style={{ fontSize: 48, marginBottom: 16, color: '#d9d9d9' }} />
            <div style={{ fontSize: 15, color: '#8c8c8c' }}>开始新的对话</div>
            <div style={{ fontSize: 13, marginTop: 8, color: '#bfbfbf' }}>
              输入你的经营目标，Agent 将自动执行
            </div>
          </div>
        )}

        {/* Messages with date grouping */}
        {messages.map((msg, idx) => {
          const prevMsg = idx > 0 ? messages[idx - 1] : null
          const showDateDivider = !prevMsg || !isSameDay(msg.created_at, prevMsg.created_at)
          return (
            <div key={msg.id}>
              {showDateDivider && <DateDivider date={msg.created_at} />}
              <MessageBubble message={msg} />
            </div>
          )
        })}

        {/* ── Streaming response area ── */}
        {isStreaming && (
          <StreamingResponse
            thinking={currentThinking}
            toolCalls={currentToolCalls}
            content={currentStreamContent}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Connection status bar */}
      {wsStatus !== 'connected' && currentSessionId && (
        <div
          style={{
            padding: '2px 24px',
            fontSize: 11,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: wsStatus === 'connecting' ? '#fffbe6' : '#fff2f0',
            color: wsStatus === 'connecting' ? '#ad8b00' : '#ff4d4f',
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <SyncOutlined spin={wsStatus === 'connecting'} />
          {wsStatus === 'connecting' ? '正在连接...' : '连接已断开'}
        </div>
      )}

      {/* Input Area */}
      <div
        style={{
          borderTop: '1px solid #f0f0f0',
          padding: '8px 24px 12px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 6,
            padding: '0 2px',
          }}
        >
          <Text type="secondary" style={{ fontSize: 11 }}>
            店铺: <Text code style={{ fontSize: 11 }}>{shopId || '未选择'}</Text>
          </Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            Enter 发送 · Shift+Enter 换行
          </Text>
        </div>
        <div
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'flex-end',
          }}
        >
          <Button
            icon={<UploadOutlined />}
            size="small"
            style={{ marginBottom: 2 }}
            disabled={isStreaming}
          />
          <TextArea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的经营目标，Agent 将自动执行..."
            autoSize={{ minRows: 1, maxRows: 4 }}
            style={{ flex: 1 }}
            disabled={isStreaming}
          />
          {isStreaming ? (
            <Button danger icon={<StopOutlined />} onClick={stop}>
              停止
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!inputValue.trim()}
            >
              发送
            </Button>
          )}
        </div>
      </div>

      {/* ── Human Confirm Dialog ── */}
      <Modal
        title={
          <Space>
            <ExclamationCircleOutlined style={{ color: '#faad14' }} />
            <span>确认操作</span>
          </Space>
        }
        open={!!confirmInfo}
        onOk={() => confirmAction(true)}
        onCancel={() => confirmAction(false)}
        okText="确认执行"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        maskClosable={false}
        closable={false}
        destroyOnClose
      >
        {confirmInfo && (
          <div style={{ padding: '12px 0' }}>
            <Alert
              type="warning"
              showIcon
              message={confirmInfo.question || '确认执行此操作？'}
              description={
                <div style={{ fontSize: 13, marginTop: 4 }}>
                  <div><strong>操作:</strong> {confirmInfo.description}</div>
                  {confirmInfo.tool && (
                    <div style={{ marginTop: 4 }}>
                      <strong>工具:</strong> <code>{confirmInfo.tool}</code>
                    </div>
                  )}
                  {!!confirmInfo.input && (
                    <div style={{ marginTop: 8 }}>
                      <strong style={{ fontSize: 12 }}>参数:</strong>
                      <pre
                        style={{
                          margin: '4px 0 0',
                          padding: 8,
                          background: '#f5f5f5',
                          borderRadius: 4,
                          fontSize: 11,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          maxHeight: 200,
                          overflowY: 'auto',
                        }}
                      >
                        {typeof confirmInfo.input === 'string'
                          ? confirmInfo.input
                          : JSON.stringify(confirmInfo.input, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              }
            />
          </div>
        )}
      </Modal>
    </div>
  )
}

/* ================================================================== */
/*  Streaming response (thinking + tool calls + text with typewriter)  */
/* ================================================================== */
interface ToolCallState {
  id: string
  name: string
  input?: unknown
  output?: unknown
  status: 'running' | 'completed' | 'error'
}

function StreamingResponse({
  thinking,
  toolCalls,
  content,
}: {
  thinking: string
  toolCalls: ToolCallState[]
  content: string
}) {
  const hasThinking = !!thinking
  const hasToolCalls = toolCalls.length > 0
  const hasContent = !!content

  if (!hasThinking && !hasToolCalls && !hasContent) {
    return (
      <div style={{ display: 'flex', marginBottom: 16, gap: 10 }}>
        <AvatarIcon role="ai" />
        <Spin size="small" style={{ marginTop: 6 }} />
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', marginBottom: 16, gap: 10 }}>
      <AvatarIcon role="ai" />
      <div style={{ maxWidth: '80%', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* Thinking block */}
        {hasThinking && (
          <div
            style={{
              background: '#fffbe6',
              borderRadius: 8,
              padding: '8px 12px',
              border: '1px solid #ffe58f',
            }}
          >
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
              🤔 思考中...
            </Text>
            <Text
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontSize: 13,
                color: '#8c8c8c',
              }}
            >
              {thinking}
            </Text>
          </div>
        )}

        {/* Tool calls (compact chips) */}
        {hasToolCalls && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {toolCalls.map((tc) => (
              <span
                key={tc.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 8px',
                  borderRadius: 4,
                  fontSize: 12,
                  background: tc.status === 'completed' ? '#f6ffed' : '#fff7e6',
                  border: tc.status === 'completed' ? '1px solid #b7eb8f' : '1px solid #ffe58f',
                }}
              >
                {tc.status === 'completed' ? (
                  <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 11 }} />
                ) : (
                  <LoadingOutlined style={{ color: '#faad14', fontSize: 11 }} />
                )}
                <Text code style={{ fontSize: 11 }}>{tc.name}</Text>
              </span>
            ))}
          </div>
        )}

        {/* Streaming text */}
        {hasContent && (
          <div
            style={{
              background: '#f5f5f5',
              borderRadius: '0 8px 8px 8px',
              padding: '10px 14px',
            }}
          >
            <MarkdownContent content={content} />
            <span className="streaming-cursor" />
          </div>
        )}
      </div>
    </div>
  )
}

/* ================================================================== */
/*  Date divider + helpers                                              */
/* ================================================================== */

function isSameDay(a: string, b: string): boolean {
  return dayjs(a).format('YYYY-MM-DD') === dayjs(b).format('YYYY-MM-DD')
}

function getDateLabel(date: string): string {
  const d = dayjs(date)
  const today = dayjs()
  if (d.isSame(today, 'day')) return '今天'
  if (d.isSame(today.subtract(1, 'day'), 'day')) return '昨天'
  return d.format('YYYY年M月D日')
}

function DateDivider({ date }: { date: string }) {
  return (
    <div style={{ textAlign: 'center', margin: '24px 0 16px' }}>
      <Text
        type="secondary"
        style={{ fontSize: 11, background: '#fff', padding: '0 12px' }}
      >
        {getDateLabel(date)}
      </Text>
      <div
        style={{
          position: 'relative',
          top: -1,
          zIndex: -1,
          borderTop: '1px solid #f0f0f0',
          marginTop: -9,
        }}
      />
    </div>
  )
}

/* ================================================================== */
/*  Single message bubble                                              */
/* ================================================================== */
function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'human') {
    return (
      <div
        style={{
          display: 'flex',
          marginBottom: 16,
          gap: 10,
          flexDirection: 'row-reverse',
        }}
      >
        <AvatarIcon role="human" />
        <div
          style={{
            background: '#e6f4ff',
            borderRadius: '8px 8px 0 8px',
            padding: '10px 14px',
            maxWidth: '80%',
          }}
        >
          <Text
            style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontSize: 14,
            }}
          >
            {message.content}
          </Text>
          <div style={{ marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {dayjs(message.created_at).format('HH:mm')}
            </Text>
          </div>
        </div>
      </div>
    )
  }

  // AI message with thinking / toolCalls / content
  if (message.role === 'ai') {
    const hasThinking = !!message.thinking
    const hasToolCalls = !!(message.toolCalls && message.toolCalls.length > 0)
    const hasContent = !!message.content

    return (
      <div
        style={{
          display: 'flex',
          marginBottom: 16,
          gap: 10,
        }}
      >
        <AvatarIcon role="ai" />
        <div style={{ maxWidth: '80%', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {/* Thinking block (collapsible) */}
          {hasThinking && (
            <Collapse
              size="small"
              ghost
              defaultActiveKey={[]}
              items={[
                {
                  key: 'thinking',
                  label: (
                    <Space size={4}>
                      <Text style={{ fontSize: 12, color: '#8c8c8c' }}>🤔 思考过程</Text>
                    </Space>
                  ),
                  children: (
                    <div
                      style={{
                        background: '#fffbe6',
                        borderRadius: 8,
                        padding: '8px 12px',
                        border: '1px solid #ffe58f',
                      }}
                    >
                      <Text
                        style={{
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontSize: 13,
                          color: '#8c8c8c',
                        }}
                      >
                        {message.thinking}
                      </Text>
                    </div>
                  ),
                },
              ]}
            />
          )}

          {/* Tool calls (compact chips) */}
          {hasToolCalls && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {message.toolCalls!.map((tc: ToolCall, idx: number) => (
                <span
                  key={idx}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 12,
                    background: tc.status === 'completed' ? '#f6ffed' : '#fff7e6',
                    border: tc.status === 'completed' ? '1px solid #b7eb8f' : '1px solid #ffe58f',
                  }}
                >
                  {tc.status === 'completed' ? (
                    <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 11 }} />
                  ) : (
                    <LoadingOutlined style={{ color: '#faad14', fontSize: 11 }} />
                  )}
                  <Text code style={{ fontSize: 11 }}>{tc.name}</Text>
                </span>
              ))}
            </div>
          )}

          {/* AI response text (Markdown) */}
          {hasContent && (
            <div
              style={{
                background: '#f5f5f5',
                borderRadius: '0 8px 8px 8px',
                padding: '10px 14px',
              }}
            >
              <MarkdownContent content={message.content} />
            </div>
          )}

          <div style={{ marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {dayjs(message.created_at).format('HH:mm')}
            </Text>
            {hasContent && (
              <CopyButton
                text={message.content}
                label="复制回复"
              />
            )}
          </div>
        </div>
      </div>
    )
  }

  // Fallback (shouldn't normally happen after grouping)
  return null
}

/* ================================================================== */
/*  Copy button                                                        */
/* ================================================================== */

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  return (
    <span
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        })
      }}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        cursor: 'pointer',
        color: copied ? '#52c41a' : '#8c8c8c',
        fontSize: 11,
        transition: 'color 0.15s',
      }}
      title={label || '复制'}
    >
      {copied ? (
        <CheckCircleOutlined style={{ fontSize: 11 }} />
      ) : (
        <CopyOutlined style={{ fontSize: 11 }} />
      )}
      {copied ? '已复制' : label || '复制'}
    </span>
  )
}

/* ================================================================== */
/*  Markdown renderer                                                  */
/* ================================================================== */
function MarkdownContent({ content }: { content: string }) {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const isInline = !className
            const match = className?.match(/language-(\w+)/)
            const lang = match?.[1] ?? ''
            if (isInline) {
              return <code className={className} {...props}>{children}</code>
            }
            const codeText = String(children).replace(/\n$/, '')
            const id = `code-${crypto.randomUUID()}`
            return (
              <div style={{ position: 'relative' }}>
                <div
                  style={{
                    position: 'absolute',
                    right: 8,
                    top: 8,
                    display: 'flex',
                    gap: 4,
                    alignItems: 'center',
                  }}
                >
                  {lang && (
                    <span
                      style={{
                        fontSize: 11,
                        color: 'rgba(255,255,255,0.5)',
                        textTransform: 'uppercase',
                      }}
                    >
                      {lang}
                    </span>
                  )}
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(codeText).then(() => {
                        setCopiedId(id)
                        setTimeout(() => setCopiedId(null), 2000)
                      })
                    }}
                    style={{
                      border: '1px solid rgba(255,255,255,0.2)',
                      background: 'rgba(255,255,255,0.1)',
                      borderRadius: 4,
                      padding: '3px 6px',
                      cursor: 'pointer',
                      color: 'rgba(255,255,255,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      fontSize: 12,
                      lineHeight: 1,
                      transition: 'all 0.15s',
                    }}
                    title="复制代码"
                  >
                    {copiedId === id ? '✓' : <CopyOutlined />}
                  </button>
                </div>
                <code className={className} {...props}>
                  {children}
                </code>
              </div>
            )
          },
          table({ children }) {
            return (
              <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                <table>{children}</table>
              </div>
            )
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

/* ================================================================== */
/*  Avatar icon                                                        */
/* ================================================================== */
function AvatarIcon({ role }: { role: 'human' | 'ai' }) {
  const isUser = role === 'human'
  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: 6,
        background: isUser ? '#f0f0f0' : '#1677ff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      {isUser ? (
        <UserOutlined style={{ color: '#666', fontSize: 16 }} />
      ) : (
        <RobotOutlined style={{ color: '#fff', fontSize: 16 }} />
      )}
    </div>
  )
}
