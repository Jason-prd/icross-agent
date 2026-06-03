import { useState, useEffect } from 'react'
import { List, Input, Button, Typography, Tooltip, Popconfirm } from 'antd'
import {
  MessageOutlined,
  DeleteOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useChatStore } from '../stores/chatStore'
import dayjs from 'dayjs'

const { Text } = Typography

export default function SessionList({ shopId }: { shopId: string }) {
  const [search, setSearch] = useState('')
  const sessions = useChatStore((s) => s.sessions)
  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const loadSessions = useChatStore((s) => s.loadSessions)
  const selectSession = useChatStore((s) => s.selectSession)
  const newSession = useChatStore((s) => s.newSession)
  const deleteSessionItem = useChatStore((s) => s.deleteSessionItem)

  useEffect(() => {
    loadSessions(shopId)
  }, [shopId, loadSessions])

  const filtered = sessions.filter(
    (s) =>
      !search || s.title.toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      {/* Header */}
      <div style={{ padding: '16px 16px 12px' }}>
        <Text strong style={{ fontSize: 15 }}>
          <MessageOutlined style={{ marginRight: 8 }} />
          对话历史
        </Text>
      </div>

      {/* Search */}
      <div style={{ padding: '0 16px 8px' }}>
        <Input
          placeholder="搜索会话..."
          prefix={<SearchOutlined />}
          size="small"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          allowClear
        />
      </div>

      {/* Session List */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {filtered.length === 0 ? (
          <div
            style={{
              padding: '40px 16px',
              textAlign: 'center',
              color: '#bbb',
              fontSize: 13,
            }}
          >
            {search ? '未找到匹配的会话' : '暂无会话，开始新对话吧'}
          </div>
        ) : (
          <List
            dataSource={filtered}
            renderItem={(item) => {
              const isActive = item.id === currentSessionId
              return (
                <List.Item
                  key={item.id}
                  onClick={() => selectSession(item.id)}
                  style={{
                    padding: '10px 16px',
                    cursor: 'pointer',
                    background: isActive ? '#e6f4ff' : 'transparent',
                    borderLeft: isActive
                      ? '3px solid #1677ff'
                      : '3px solid transparent',
                    transition: 'all 0.15s',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    borderBottom: '1px solid #f5f5f5',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      ;(
                        e.currentTarget as HTMLElement
                      ).style.background = '#f5f5f5'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      ;(
                        e.currentTarget as HTMLElement
                      ).style.background = 'transparent'
                    }
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Text
                      style={{
                        fontSize: 13,
                        display: 'block',
                        fontWeight: isActive ? 500 : 400,
                      }}
                      ellipsis
                    >
                      {item.title || '新会话'}
                    </Text>
                    <div
                      style={{
                        display: 'flex',
                        gap: 8,
                        marginTop: 4,
                      }}
                    >
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {dayjs(
                          item.updated_at || item.created_at,
                        ).format('MM-DD HH:mm')}
                      </Text>
                      {item.message_count != null && (
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {item.message_count} 条消息
                        </Text>
                      )}
                    </div>
                  </div>

                  <span
                    onClick={(e) => e.stopPropagation()}
                    style={{ flexShrink: 0, marginLeft: 8 }}
                  >
                    <Popconfirm
                      title="确定删除此会话？"
                      onConfirm={() => deleteSessionItem(item.id)}
                      placement="left"
                    >
                      <Tooltip title="删除">
                        <DeleteOutlined
                          style={{
                            color: '#999',
                            fontSize: 13,
                            opacity: 0.4,
                            transition: 'opacity 0.15s',
                          }}
                          className="delete-icon"
                          onMouseEnter={(e) => {
                            ;(
                              e.currentTarget as HTMLElement
                            ).style.opacity = '1'
                          }}
                          onMouseLeave={(e) => {
                            ;(
                              e.currentTarget as HTMLElement
                            ).style.opacity = '0.4'
                          }}
                        />
                      </Tooltip>
                    </Popconfirm>
                  </span>
                </List.Item>
              )
            }}
          />
        )}
      </div>

      {/* New Chat Button */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid #f0f0f0',
        }}
      >
        <Button
          type="primary"
          block
          icon={<PlusOutlined />}
          onClick={newSession}
        >
          新对话
        </Button>
      </div>
    </div>
  )
}
