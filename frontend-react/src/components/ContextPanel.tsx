import { useState, useEffect, useCallback } from 'react'
import { Card, Typography, Space, Tag, Spin, Steps, Button, Divider, Modal, Form, Input, InputNumber, message } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  MinusCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import client from '../api/client'
import { useChatStore } from '../stores/chatStore'
import { listShops, createShop, authenticateShop, type Shop, type ShopCreatePayload } from '../api/shops'

const { Text } = Typography

interface ContextPanelProps {
  shopId: string
}

interface AgentStatus {
  status: string
  has_active_task: boolean
  current_tool?: string
  current_step?: number
  error?: string
  started_at?: string
}

interface WorkflowStepEvent {
  type: 'workflow_step'
  step: number
  tools?: string[]
  status: 'pending' | 'running' | 'completed'
  description?: string
}

export default function ContextPanel({ shopId }: ContextPanelProps) {
  const currentSessionId = useChatStore((s) => s.currentSessionId)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const selectedShopIds = useChatStore((s) => s.selectedShopIds)
  const setSelectedShopIds = useChatStore((s) => s.setSelectedShopIds)

  const [shops, setShops] = useState<Shop[]>([])
  const [shopsLoading, setShopsLoading] = useState(false)
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null)
  const [apiVerified, setApiVerified] = useState<Map<string, boolean | null>>(new Map())
  const [runningShops, setRunningShops] = useState<Set<string>>(new Set())
  const [steps, setSteps] = useState<WorkflowStepEvent[]>([])

  // ── Add-shop modal state ──
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const [addForm] = Form.useForm()

  // ── Fetch all shops ──
  const fetchShops = useCallback(() => {
    setShopsLoading(true)
    listShops()
      .then(setShops)
      .catch(() => setShops([]))
      .finally(() => setShopsLoading(false))
  }, [])

  useEffect(() => {
    fetchShops()
  }, [fetchShops])

  // ── Verify API for each shop every time the shop list changes ──
  useEffect(() => {
    const m = new Map<string, boolean | null>()
    shops.forEach((s) => m.set(s.shop_id, null))
    setApiVerified(m)

    shops.forEach((s) => {
      authenticateShop(s.shop_id).then((ok) => {
        setApiVerified((prev) => {
          const next = new Map(prev)
          next.set(s.shop_id, ok)
          return next
        })
      })
    })
  }, [shops])

  // ── Poll agent status + events for current session ──
  useEffect(() => {
    if (!currentSessionId) {
      setAgentStatus(null)
      setSteps([])
      return
    }

    const fetchStatus = () => {
      client
        .get(`/api/sessions/${currentSessionId}/agent-status`)
        .then((res) => setAgentStatus(res.data))
        .catch(() => {})
    }

    const fetchEvents = () => {
      client
        .get(`/api/sessions/${currentSessionId}/agent-events?since=0`)
        .then((res) => {
          const allEvents: unknown[] = res.data.events ?? []
          const workflowSteps = allEvents.filter(
            (e): e is WorkflowStepEvent =>
              typeof e === 'object' && e !== null && (e as Record<string, unknown>).type === 'workflow_step',
          )
          if (workflowSteps.length > 0) {
            setSteps(workflowSteps)
          }
        })
        .catch(() => {})
    }

    fetchStatus()
    fetchEvents()
    const interval = setInterval(() => {
      fetchStatus()
      fetchEvents()
    }, 3000)
    return () => clearInterval(interval)
  }, [currentSessionId])

  // ── Auto-select first shop on initial load ──
  useEffect(() => {
    if (shops.length > 0 && selectedShopIds.length === 0) {
      setSelectedShopIds([shops[0].shop_id])
    }
  }, [shops, selectedShopIds, setSelectedShopIds])

  // ── Shop selection toggle ──
  const toggleShop = useCallback(
    (id: string) => {
      setSelectedShopIds(
        selectedShopIds.includes(id)
          ? selectedShopIds.filter((sid) => sid !== id)
          : [...selectedShopIds, id],
      )
    },
    [selectedShopIds, setSelectedShopIds],
  )

  // ── Add-shop handler ──
  const handleAddShop = async () => {
    try {
      const values = await addForm.validateFields()
      setAdding(true)
      await createShop(values as ShopCreatePayload)
      message.success('店铺添加成功')
      setAddModalOpen(false)
      addForm.resetFields()
      fetchShops()
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return // Ant Design form validation error, do nothing
      }
      message.error('添加店铺失败')
    } finally {
      setAdding(false)
    }
  }

  // ── Per-shop auto-pilot handler ──
  const handleShopAutoPilot = async (targetShopId: string) => {
    if (runningShops.has(targetShopId) || isStreaming) return
    setRunningShops((prev) => new Set(prev).add(targetShopId))
    try {
      const { data } = await client.get(`/api/auto-pilot/prompt/${targetShopId}`)
      const prompt = data.prompt || ''
      const store = useChatStore.getState()
      store.newSession()
      store.setSelectedShopIds([targetShopId])
      setTimeout(() => {
        store.sendMessage(
          prompt || `请执行自动运营任务，店铺ID: ${targetShopId}`,
          targetShopId,
        )
        setRunningShops((prev) => {
          const next = new Set(prev)
          next.delete(targetShopId)
          return next
        })
      }, 100)
    } catch {
      const store = useChatStore.getState()
      store.newSession()
      store.setSelectedShopIds([targetShopId])
      setTimeout(() => {
        store.sendMessage(
          `请执行自动运营任务，店铺ID: ${targetShopId}`,
          targetShopId,
        )
        setRunningShops((prev) => {
          const next = new Set(prev)
          next.delete(targetShopId)
          return next
        })
      }, 100)
    }
  }

  const taskStatus = agentStatus?.status ?? 'idle'
  const stepItems = buildStepItems(steps, taskStatus)

  return (
    <div
      style={{
        padding: '16px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      {/* ═══════════════════ 店铺信息 ═══════════════════ */}
      <div style={{ flex: '0 0 auto' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 8,
          }}
        >
          <Text strong style={{ fontSize: 13, color: '#8c8c8c' }}>
            店铺信息
          </Text>
          <Button
            size="small"
            type="dashed"
            icon={<PlusOutlined />}
            onClick={() => setAddModalOpen(true)}
          >
            添加
          </Button>
        </div>

        {shopsLoading ? (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <Spin size="small" />
          </div>
        ) : shops.length === 0 ? (
          <div
            style={{
              textAlign: 'center',
              color: '#bbb',
              fontSize: 12,
              padding: '16px 0',
            }}
          >
            暂无店铺，点击「添加」新增
          </div>
        ) : (
          /* Scrollable shop cards area */
          <div style={{ maxHeight: 260, overflowY: 'auto' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {shops.map((shop) => {
                const selected = selectedShopIds.includes(shop.shop_id)
                const verified = apiVerified.get(shop.shop_id) ?? null
                const running = runningShops.has(shop.shop_id)
                return (
                  <ShopCard
                    key={shop.shop_id}
                    shop={shop}
                    selected={selected}
                    verified={verified}
                    running={running}
                    onClick={() => toggleShop(shop.shop_id)}
                    onAutoPilot={() => handleShopAutoPilot(shop.shop_id)}
                  />
                )
              })}
            </div>
          </div>
        )}
      </div>

      <Divider style={{ margin: '2px 0' }} />

      {/* ═══════════════════ 会话工作流 ═══════════════════ */}
      <Text strong style={{ fontSize: 13, color: '#8c8c8c', flex: '0 0 auto' }}>
        会话工作流
      </Text>

      {currentSessionId ? (
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <Card size="small" style={{ width: '100%' }}>
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              {/* Status badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {taskStatus === 'running' ? (
                  <SyncOutlined spin style={{ color: '#1677ff' }} />
                ) : taskStatus === 'completed' ? (
                  <CheckCircleOutlined style={{ color: '#52c41a' }} />
                ) : taskStatus === 'failed' || taskStatus === 'error' ? (
                  <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                ) : (
                  <MinusCircleOutlined style={{ color: '#d9d9d9' }} />
                )}
                <Text style={{ fontSize: 13 }}>
                  {taskStatus === 'idle' && '等待中'}
                  {taskStatus === 'running' && '运行中'}
                  {taskStatus === 'completed' && '已完成'}
                  {taskStatus === 'failed' && '失败'}
                  {taskStatus === 'interrupted' && '已中断'}
                  {taskStatus === 'pending' && '排队中'}
                </Text>
              </div>

              {/* Workflow steps */}
              {stepItems.length > 0 && (
                <Steps
                  direction="vertical"
                  size="small"
                  current={stepItems.findIndex((s) => s.status === 'process')}
                  items={stepItems}
                  style={{ fontSize: 12, marginTop: 4 }}
                />
              )}

              {/* Empty state hint */}
              {stepItems.length === 0 && taskStatus === 'idle' && (
                <div
                  style={{
                    textAlign: 'center',
                    color: '#bbb',
                    fontSize: 12,
                    padding: '12px 0',
                  }}
                >
                  输入经营目标或点击店铺卡片「自动运营」开始
                </div>
              )}
            </Space>
          </Card>
        </div>
      ) : (
        <div
          style={{
            textAlign: 'center',
            color: '#bbb',
            fontSize: 12,
            padding: '20px 0',
          }}
        >
          选择一个会话或点击店铺卡片「自动运营」开始
        </div>
      )}

      {/* ═══════════════════ 添加店铺弹窗 ═══════════════════ */}
      <Modal
        title="添加店铺"
        open={addModalOpen}
        onOk={handleAddShop}
        onCancel={() => {
          setAddModalOpen(false)
          addForm.resetFields()
        }}
        confirmLoading={adding}
        okText="添加"
        cancelText="取消"
        destroyOnClose
      >
        <Form
          form={addForm}
          layout="vertical"
          size="small"
          initialValues={{ sync_days: 90 }}
        >
          <Form.Item
            name="shop_id"
            label="店铺 ID"
            rules={[{ required: true, message: '请输入店铺 ID' }]}
          >
            <Input placeholder="Ozon 店铺唯一标识" />
          </Form.Item>
          <Form.Item name="name" label="店铺名称">
            <Input placeholder="可选，默认与店铺 ID 相同" />
          </Form.Item>
          <Form.Item
            name="client_id"
            label="Client ID"
            rules={[{ required: true, message: '请输入 Client ID' }]}
          >
            <Input placeholder="Ozon API Client ID" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={[{ required: true, message: '请输入 API Key' }]}
          >
            <Input.Password placeholder="Ozon API Key" />
          </Form.Item>
          <Form.Item name="token" label="Token">
            <Input.Password placeholder="可选，OAuth Token" />
          </Form.Item>
          <Form.Item name="sync_days" label="同步天数">
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

/* ================================================================== */
/*  Small selectable shop card                                         */
/* ================================================================== */

interface ShopCardProps {
  shop: Shop
  selected: boolean
  verified: boolean | null
  running: boolean
  onClick: () => void
  onAutoPilot: () => void
}

function ShopCard({ shop, selected, verified, running, onClick, onAutoPilot }: ShopCardProps) {
  return (
    <div
      style={{
        borderRadius: 6,
        border: `1px solid ${selected ? '#1677ff' : '#f0f0f0'}`,
        background: selected ? '#e6f4ff' : '#fff',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 140,
        flex: '1 0 auto',
        maxWidth: '100%',
        transition: 'all 0.15s',
        userSelect: 'none',
        overflow: 'hidden',
      }}
    >
      {/* Shop info body — click to toggle selection */}
      <div
        onClick={onClick}
        style={{
          padding: '6px 10px 4px',
          cursor: 'pointer',
          display: 'flex',
          flexDirection: 'column',
          gap: 3,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {selected && (
            <CheckCircleOutlined style={{ color: '#1677ff', fontSize: 11 }} />
          )}
          <Text
            style={{ fontSize: 12, fontWeight: selected ? 600 : 400 }}
            ellipsis
          >
            {shop.name}
          </Text>
        </div>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <Tag
            style={{
              fontSize: 10,
              lineHeight: '16px',
              padding: '0 4px',
              margin: 0,
              maxWidth: 70,
            }}
          >
            {shop.shop_id}
          </Tag>
          {verified === true && (
            <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 10 }} />
          )}
          {verified === false && (
            <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 10 }} />
          )}
          {verified === null && (
            <SyncOutlined spin style={{ color: '#d9d9d9', fontSize: 10 }} />
          )}
        </div>
      </div>

      {/* Per-shop auto-pilot button */}
      <div
        onClick={(e) => {
          e.stopPropagation()
          if (!running) onAutoPilot()
        }}
        style={{
          borderTop: `1px solid ${selected ? '#91caff' : '#f0f0f0'}`,
          padding: '3px 0',
          textAlign: 'center',
          fontSize: 11,
          color: running ? '#1677ff' : '#8c8c8c',
          cursor: running ? 'default' : 'pointer',
          transition: 'all 0.15s',
        }}
        onMouseEnter={(e) => {
          if (!running) (e.currentTarget as HTMLElement).style.color = '#1677ff'
        }}
        onMouseLeave={(e) => {
          if (!running) (e.currentTarget as HTMLElement).style.color = '#8c8c8c'
        }}
      >
        {running ? (
          <span>
            <SyncOutlined spin style={{ marginRight: 4 }} />
            运行中...
          </span>
        ) : (
          <span>
            <PlayCircleOutlined style={{ marginRight: 4 }} />
            自动运营
          </span>
        )}
      </div>
    </div>
  )
}

/* ================================================================== */
/*  Build step items for workflow Steps component                      */
/* ================================================================== */

function buildStepItems(
  steps: WorkflowStepEvent[],
  taskStatus: string,
): { title: string; description?: string; status: 'wait' | 'process' | 'finish' | 'error' }[] {
  if (steps.length === 0) {
    if (taskStatus === 'idle' || taskStatus === 'pending') {
      return [{ title: '等待指令', status: 'wait' }]
    }
    if (taskStatus === 'running') {
      return [{ title: '分析中...', status: 'process' }]
    }
    return []
  }

  const stepMap = new Map<number, WorkflowStepEvent>()
  for (const s of steps) {
    stepMap.set(s.step, s)
  }
  const uniqueSteps = Array.from(stepMap.entries())
    .sort(([a], [b]) => a - b)
    .map(([_, s]) => s)

  return uniqueSteps.map((s) => ({
    title: s.description || `步骤 ${s.step + 1}`,
    description: s.tools?.join(', '),
    status: s.status === 'running'
      ? ('process' as const)
      : s.status === 'completed'
        ? ('finish' as const)
        : ('wait' as const),
  }))
}
