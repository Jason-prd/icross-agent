import { useState } from 'react'
import { Card, Tabs, Row, Col, Badge, Input, Button, List, message, Space, Modal, Typography, Empty, Segmented, Avatar, Tag, Alert, Tooltip } from 'antd'
import {
  SendOutlined,
  MessageOutlined,
  QuestionCircleOutlined,
  StarOutlined,
  UserOutlined,
  ArrowLeftOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

const { TextArea } = Input
const { Text, Title } = Typography

interface ChatMessage {
  id: string
  text: string
  author_name: string
  created_at: string
}

interface Question {
  id: string
  question: string
  answer: string | null
  product_name: string
  created_at: string
}

interface Review {
  id: string
  text: string
  product_name: string
  score: number
  created_at: string
  answered: boolean
}

/* ── Chats Tab — 3-pane layout ── */
function ChatsTab({ currentShop }: { currentShop: string }) {
  const queryClient = useQueryClient()
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [replyText, setReplyText] = useState('')
  const [aiReply, setAiReply] = useState<any>(null); const [showAiReply, setShowAiReply] = useState(false)
  const aiReplyMutation = useMutation({mutationFn: async () => {const {data}=await axios.post(`/api/service/ai/suggest-reply/${selectedChatId}`,null,{params:{shop_id:currentShop}});return data},onSuccess:(d:any)=>{setAiReply(d);setShowAiReply(true)},onError:(e:any)=>message.error('AI 失败')})

  const { data: unreadData } = useQuery({
    queryKey: ['chat-unread', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/chat/unread', { params: { shop_id: currentShop } })
      return data
    },
    refetchInterval: 30_000,
  })

  const { data: chatHistory, isLoading } = useQuery({
    queryKey: ['chat-history', currentShop, selectedChatId],
    queryFn: async () => {
      const params: any = { shop_id: currentShop }
      if (selectedChatId) params.chat_id = selectedChatId
      const { data } = await axios.get('/api/ozon/chat/history', { params })
      return data
    },
  })

  const sendMutation = useMutation({
    mutationFn: async () => {
      if (!selectedChatId) return
      await axios.post('/api/ozon/chat/send', { chat_id: selectedChatId, text: replyText, shop_id: currentShop })
    },
    onSuccess: () => {
      message.success('消息已发送')
      setReplyText('')
      queryClient.invalidateQueries({ queryKey: ['chat-history'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '发送失败'),
  })

  const chats: ChatMessage[] = chatHistory?.chats || chatHistory?.messages || chatHistory?.items || []
  const unread = unreadData?.unread_count || 0

  // Group by chat ID (use first message text as title)
  const chatGroups = chats.reduce<Record<string, { id: string; name: string; lastMsg: string; time: string; unread: boolean }>>((acc, msg) => {
    if (!acc[msg.id]) {
      acc[msg.id] = { id: msg.id, name: msg.author_name, lastMsg: msg.text, time: msg.created_at, unread: true }
    } else {
      acc[msg.id].lastMsg = msg.text
      acc[msg.id].time = msg.created_at
    }
    return acc
  }, {})

  const chatList = Object.values(chatGroups).sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())

  return (
    <div style={{ display: 'flex', gap: 12, minHeight: 500 }}>
      {/* Left — Chat list */}
      <Card
        size="small"
        title={
          <Space>
            <Badge count={unread} size="small">
              <MessageOutlined />
            </Badge>
            <span>会话 ({chatList.length})</span>
          </Space>
        }
        style={{ width: 280, flexShrink: 0 }}
        styles={{ body: { padding: 0, overflow: 'auto', maxHeight: 480 } }}
      >
        {chatList.length === 0 ? (
          <Empty description="暂无会话" style={{ padding: 24 }} />
        ) : (
          chatList.map((chat) => (
            <div
              key={chat.id}
              onClick={() => setSelectedChatId(chat.id)}
              style={{
                padding: '10px 14px',
                cursor: 'pointer',
                borderBottom: '1px solid #f5f5f5',
                background: selectedChatId === chat.id ? '#f0f5ff' : 'transparent',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => { if (selectedChatId !== chat.id) e.currentTarget.style.background = '#fafafa' }}
              onMouseLeave={(e) => { if (selectedChatId !== chat.id) e.currentTarget.style.background = 'transparent' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <Avatar size={24} icon={<UserOutlined />} style={{ flexShrink: 0, background: '#e6f4ff', color: '#1677FF' }} />
                <Text strong style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {chat.name}
                </Text>
                {chat.unread && <Badge status="processing" />}
              </div>
              <Text type="secondary" style={{ fontSize: 12, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingLeft: 32 }}>
                {chat.lastMsg}
              </Text>
            </div>
          ))
        )}
      </Card>

      {/* Center + Right — Messages + Reply */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {selectedChatId ? (
          <>
            <Card
              size="small"
              styles={{ body: { padding: 12, overflow: 'auto', maxHeight: 360, flex: 1 } }}
              style={{ marginBottom: 8, flex: 1 }}
            >
              {isLoading ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>加载中…</div>
              ) : (
                chats.map((msg, i) => (
                  <div
                    key={i}
                    style={{
                      marginBottom: 10,
                      padding: '8px 12px',
                      borderRadius: 8,
                      background: msg.author_name === 'seller' ? '#e6f4ff' : '#f5f5f5',
                      maxWidth: '80%',
                      marginLeft: msg.author_name === 'seller' ? 'auto' : 0,
                    }}
                  >
                    <div style={{ fontSize: 12, color: '#999', marginBottom: 4 }}>
                      {msg.author_name} · {new Date(msg.created_at).toLocaleString('zh-CN')}
                    </div>
                    <div style={{ fontSize: 13, lineHeight: '20px' }}>{msg.text}</div>
                  </div>
                ))
              )}
            </Card>

            <Card size="small" styles={{ body: { padding: 10 } }}>
              <Space.Compact style={{ width: '100%' }}>
                <Input.TextArea
                  rows={2}
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  placeholder="输入回复内容…"
                  onPressEnter={(e) => {
                    if (!e.shiftKey) { e.preventDefault(); sendMutation.mutate() }
                  }}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={() => sendMutation.mutate()}
                  loading={sendMutation.isPending}
                  style={{ height: 'auto' }}
                >
                  发送
                </Button>
              </Space.Compact>
            </Card>
          </>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#bbb' }}>
            <div style={{ textAlign: 'center' }}>
              <MessageOutlined style={{ fontSize: 40, marginBottom: 12, opacity: 0.3 }} />
              <div>选择一个会话查看消息</div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Questions Tab ── */
function QuestionsTab({ currentShop }: { currentShop: string }) {
  const [page, setPage] = useState(1)
  const [answerModal, setAnswerModal] = useState<{ visible: boolean; questionId: string }>({ visible: false, questionId: '' })
  const [answerText, setAnswerText] = useState('')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['ozon-questions', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/questions', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const answerMutation = useMutation({
    mutationFn: async () => {
      await axios.post('/api/ozon/questions/answer', { question_id: answerModal.questionId, answer: answerText, shop_id: currentShop })
    },
    onSuccess: () => {
      message.success('已回答'); setAnswerModal({ visible: false, questionId: '' }); setAnswerText('')
      queryClient.invalidateQueries({ queryKey: ['ozon-questions'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '回答失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.post('/api/ozon/questions/delete', { question_id: id, shop_id: currentShop })
    },
    onSuccess: () => { message.success('已删除'); queryClient.invalidateQueries({ queryKey: ['ozon-questions'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '删除失败'),
  })

  const questions: Question[] = data?.questions || data?.items || []
  const total = data?.total || 0

  return (
    <>
      <DataTable
        columns={[
          { key: 'question', title: '问题', dataIndex: 'question', width: 260 },
          { key: 'product_name', title: '商品', dataIndex: 'product_name', width: 160 },
          { key: 'answer', title: '回答', dataIndex: 'answer', width: 200, render: (v: string | null) => v || <Text type="secondary">待回答</Text> },
          { key: 'created_at', title: '时间', dataIndex: 'created_at', width: 150, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
          {
            key: 'actions', title: '操作', width: 140,
            render: (_: any, record: Question) => (
              <Space size="small">
                {!record.answer && (
                  <Button size="small" type="primary" onClick={() => setAnswerModal({ visible: true, questionId: record.id })}>回答</Button>
                )}
                <Button size="small" danger onClick={() => deleteMutation.mutate(record.id)}>删除</Button>
              </Space>
            ),
          },
        ]}
        data={questions}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={20}
        onChange={(p) => setPage(p)}
        emptyText="暂无买家提问"
      />

      <Modal
        title="回答买家提问"
        open={answerModal.visible}
        onCancel={() => setAnswerModal({ visible: false, questionId: '' })}
        onOk={() => answerMutation.mutate()}
        confirmLoading={answerMutation.isPending}
      >
        <TextArea rows={4} value={answerText} onChange={(e) => setAnswerText(e.target.value)} placeholder="输入回答…" />
      </Modal>
    </>
  )
}

/* ── Reviews Tab ── */
function ReviewsTab({ currentShop }: { currentShop: string }) {
  const [page, setPage] = useState(1)
  const [replyModal, setReplyModal] = useState<{ visible: boolean; reviewId: string }>({ visible: false, reviewId: '' })
  const [replyText, setReplyText] = useState('')
  const [aiReply, setAiReply] = useState<any>(null); const [showAiReply, setShowAiReply] = useState(false)
  const aiReplyMutation = useMutation({mutationFn: async () => {const {data}=await axios.post(`/api/service/ai/suggest-reply/${selectedChatId}`,null,{params:{shop_id:currentShop}});return data},onSuccess:(d:any)=>{setAiReply(d);setShowAiReply(true)},onError:(e:any)=>message.error('AI 失败')})
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['ozon-reviews', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/reviews', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const replyMutation = useMutation({
    mutationFn: async () => {
      await axios.post('/api/ozon/reviews/reply', { review_id: replyModal.reviewId, text: replyText, shop_id: currentShop })
    },
    onSuccess: () => {
      message.success('已回复'); setReplyModal({ visible: false, reviewId: '' }); setReplyText('')
      queryClient.invalidateQueries({ queryKey: ['ozon-reviews'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '回复失败'),
  })

  const reviews: Review[] = data?.reviews || data?.items || []
  const total = data?.total || 0

  return (
    <>
      <DataTable
        columns={[
          { key: 'text', title: '评价内容', dataIndex: 'text', width: 280 },
          { key: 'product_name', title: '商品', dataIndex: 'product_name', width: 160 },
          { key: 'score', title: '评分', dataIndex: 'score', width: 70, render: (v: number) => (
            <span style={{ color: '#f59e0b' }}>{'★'.repeat(v)}{'☆'.repeat(5 - v)}</span>
          )},
          { key: 'created_at', title: '时间', dataIndex: 'created_at', width: 150, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
          {
            key: 'actions', title: '操作', width: 100,
            render: (_: any, record: Review) => (
              <Button size="small" type="primary" onClick={() => setReplyModal({ visible: true, reviewId: record.id })} disabled={record.answered}>
                {record.answered ? '已回复' : '回复'}
              </Button>
            ),
          },
        ]}
        data={reviews}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={20}
        onChange={(p) => setPage(p)}
        emptyText="暂无评价"
      />

      <Modal
        title="回复评价"
        open={replyModal.visible}
        onCancel={() => setReplyModal({ visible: false, reviewId: '' })}
        onOk={() => replyMutation.mutate()}
        confirmLoading={replyMutation.isPending}
      >
        <TextArea rows={4} value={replyText} onChange={(e) => setReplyText(e.target.value)} placeholder="输入回复…" />
      </Modal>
    </>
  )
}

/* ── Inbox Tab — unified attention view ── */
function InboxTab({ currentShop }: { currentShop: string }) {
  const { data: unreadData } = useQuery({
    queryKey: ['chat-unread', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/chat/unread', { params: { shop_id: currentShop } })
      return data
    },
    refetchInterval: 30_000,
  })

  const { data: questionsData } = useQuery({
    queryKey: ['ozon-questions-inbox', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/questions', { params: { shop_id: currentShop, limit: 5, answered: false } })
      return data
    },
  })

  const { data: reviewsData } = useQuery({
    queryKey: ['ozon-reviews-inbox', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/reviews', { params: { shop_id: currentShop, limit: 5 } })
      return data
    },
  })

  const unread = unreadData?.unread_count || 0
  const unanswered = questionsData?.total || questionsData?.questions?.length || 0
  const unreplied = reviewsData?.reviews?.filter((r: Review) => !r.answered).length || 0

  return (
    <Row gutter={[12, 12]}>
      <Col xs={24} sm={8}>
        <Card hoverable styles={{ body: { padding: 20 } }}>
          <div style={{ textAlign: 'center' }}>
            <Badge count={unread} style={{ backgroundColor: '#1677FF' }}>
              <MessageOutlined style={{ fontSize: 28, color: '#1677FF', padding: 4 }} />
            </Badge>
            <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>{unread}</div>
            <Text type="secondary">未读会话</Text>
          </div>
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable styles={{ body: { padding: 20 } }}>
          <div style={{ textAlign: 'center' }}>
            <Badge count={unanswered} style={{ backgroundColor: '#f59e0b' }}>
              <QuestionCircleOutlined style={{ fontSize: 28, color: '#f59e0b', padding: 4 }} />
            </Badge>
            <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>{unanswered}</div>
            <Text type="secondary">待回答问题</Text>
          </div>
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable styles={{ body: { padding: 20 } }}>
          <div style={{ textAlign: 'center' }}>
            <Badge count={unreplied} style={{ backgroundColor: '#22c55e' }}>
              <StarOutlined style={{ fontSize: 28, color: '#22c55e', padding: 4 }} />
            </Badge>
            <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>{unreplied}</div>
            <Text type="secondary">未回复评价</Text>
          </div>
        </Card>
      </Col>
    </Row>
  )
}

/* ── Main ── */
export default function Service() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  return (
    <div>
      <PageHeader title="客服中心" subtitle="买家会话 / 问答 / 评价 — 统一服务台" />
      <Tabs
        items={[
          { key: 'inbox', label: '服务概览', children: <InboxTab currentShop={currentShop} /> },
          { key: 'chats', label: '买家会话', children: <ChatsTab currentShop={currentShop} /> },
          { key: 'questions', label: '买家问答', children: <QuestionsTab currentShop={currentShop} /> },
          { key: 'reviews', label: '商品评价', children: <ReviewsTab currentShop={currentShop} /> },
        ]}
      />
    </div>
  )
}
