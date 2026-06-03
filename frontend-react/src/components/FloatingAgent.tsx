import { useState, useRef, useEffect } from 'react'
import { Input, Button, Typography, Space, Spin, Tooltip, Badge } from 'antd'
import { SendOutlined, CloseOutlined, RobotOutlined, UserOutlined, StopOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '../stores/chatStore'
import { useWebSocket } from '../hooks/useWebSocket'

const { Text } = Typography
const { TextArea } = Input

export default function FloatingAgent({ shopId }: { shopId: string }) {
  const [open, setOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const messages = useChatStore((s) => s.messages)
  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const currentStreamContent = useChatStore((s) => s.currentStreamContent)
  const currentThinking = useChatStore((s) => s.currentThinking)
  const { send, stop } = useWebSocket()

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentStreamContent, currentThinking])

  const handleSend = () => {
    const text = inputValue.trim()
    if (!text) return
    send(text, shopId)
    setInputValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Limit messages displayed in compact view
  const displayMessages = messages.slice(-12)

  return (
    <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 1050, display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
      {/* Chat panel */}
      {open && (
        <div
          style={{
            width: 400,
            height: 520,
            background: '#fff',
            borderRadius: 12,
            boxShadow: '0 8px 40px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,0,0,0.04)',
            display: 'flex',
            flexDirection: 'column',
            marginBottom: 12,
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 16px',
              borderBottom: '1px solid #f0f0f0',
              background: '#fafafa',
            }}
          >
            <Space>
              <RobotOutlined style={{ color: '#1677FF', fontSize: 16 }} />
              <Text strong style={{ fontSize: 14 }}>AI 助手</Text>
              {!currentSessionId && (
                <span style={{ fontSize: 11, color: '#999', background: '#f0f0f0', padding: '1px 6px', borderRadius: 4 }}>
                  新会话
                </span>
              )}
            </Space>
            <Button type="text" size="small" icon={<CloseOutlined />} onClick={() => setOpen(false)} />
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflow: 'auto', padding: '8px 12px' }}>
            {displayMessages.length === 0 && !isStreaming ? (
              <div style={{ textAlign: 'center', padding: '60px 20px', color: '#bbb' }}>
                <RobotOutlined style={{ fontSize: 32, marginBottom: 8, opacity: 0.4 }} />
                <div style={{ fontSize: 13 }}>有什么需要帮忙的吗？</div>
                <div style={{ fontSize: 11, marginTop: 4, color: '#d0d0d0' }}>可以查询订单、商品信息或操作店铺</div>
              </div>
            ) : (
              <>
                {displayMessages.map((msg, i) => {
                  const isUser = msg.role === 'human'
                  return (
                  <div key={i} style={{ marginBottom: 10, display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
                    <div
                      style={{
                        maxWidth: '85%',
                        padding: '8px 12px',
                        borderRadius: 10,
                        background: isUser ? '#1677FF' : '#f5f5f5',
                        color: isUser ? '#fff' : '#374151',
                        fontSize: 13,
                        lineHeight: '20px',
                      }}
                    >
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content || ''}
                      </ReactMarkdown>
                    </div>
                  </div>
                )})}
                {/* Streaming content */}
                {isStreaming && currentStreamContent && (
                  <div style={{ marginBottom: 10, display: 'flex', justifyContent: 'flex-start' }}>
                    <div style={{ maxWidth: '85%', padding: '8px 12px', borderRadius: 10, background: '#f5f5f5', fontSize: 13, lineHeight: '20px' }}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {currentStreamContent}
                      </ReactMarkdown>
                    </div>
                  </div>
                )}

                {/* Thinking indicator */}
                {isStreaming && currentThinking && (
                  <div style={{ marginBottom: 8, padding: '4px 12px', fontSize: 11, color: '#999' }}>
                    <Spin size="small" style={{ marginRight: 6 }} />
                    AI 思考中…
                  </div>
                )}
              </>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div style={{ padding: '8px 12px 12px', borderTop: '1px solid #f0f0f0' }}>
            <Space.Compact style={{ width: '100%' }}>
              <TextArea
                rows={2}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入指令…"
                style={{ fontSize: 13, resize: 'none' }}
              />
              {isStreaming ? (
                <Button icon={<StopOutlined />} onClick={stop} danger style={{ height: 'auto' }} />
              ) : (
                <Button type="primary" icon={<SendOutlined />} onClick={handleSend} style={{ height: 'auto' }} disabled={!inputValue.trim()} />
              )}
            </Space.Compact>
          </div>
        </div>
      )}

      {/* FAB button */}
      <Tooltip title={open ? '关闭' : 'AI 助手'} placement="left">
        <Badge count={messages.filter((m) => m.role === 'ai' && !open).length} size="small" offset={[-4, 4]}>
          <Button
            type="primary"
            shape="circle"
            size="large"
            icon={open ? <CloseOutlined /> : <RobotOutlined />}
            onClick={() => setOpen(!open)}
            style={{
              width: 48,
              height: 48,
              boxShadow: '0 4px 16px rgba(22,119,255,0.35)',
              fontSize: 20,
            }}
          />
        </Badge>
      </Tooltip>
    </div>
  )
}
