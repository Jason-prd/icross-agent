import { useState, useEffect, useCallback } from 'react'
import {
  Card, Table, Modal, Form, Input, InputNumber, Button, message, Space, Typography,
  Popconfirm, Tag, Row, Col, Select, Descriptions, Tooltip, Layout, Menu,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  ApiOutlined, RobotOutlined, ShopOutlined, BellOutlined,
  CheckCircleOutlined, CloseCircleOutlined, KeyOutlined, SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import PageHeader from '../components/PageHeader'
import StatusTag from '../components/StatusTag'
import client from '../api/client'

const { Text } = Typography
const { Content, Sider } = Layout

// ──────────────────────────── Types ────────────────────────────

interface ProviderItem {
  id: string
  name: string
  transport: string
  default_model: string
  base_url: string
  api_key: string
  has_api_key: boolean
  api_key_env: string
  context_length: number
  doc: string
}

interface ShopItem {
  shop_id: string
  name: string
  client_id: string
  api_key: string
  token: string
  status: string
  sync_days?: number
  created_at?: string
}

interface NotifyChannel {
  name: string
  platform: string
  chat_id: string
}

interface NotifyChannelsData {
  ready: boolean
  channels: Record<string, NotifyChannel>
  adapters: Record<string, any>
  available_platforms: string[]
}

// ──────────────────────────── Constants ────────────────────────────

const MODULE_LABELS: Record<string, string> = {
  product: '商品', order: '订单', return: '退货', category: '类目',
  listing: 'Listing', session: '会话', agent: '智能体',
}

const FEATURE_LABELS: Record<string, string> = {
  'product.title.optimize': '标题优化', 'product.description.generate': '描述生成',
  'product.attributes.complete': '属性补全', 'product.quality.check': '质量检查',
  'product.price.suggest': '定价建议', 'category.match': '类目匹配',
  'category.list': '类目列表', 'listing.generate': 'Listing 生成',
  'session.title.summarize': '会话摘要', 'agent.main': '主 Agent',
  'product.parse': '商品解析', 'order.max_purchase_price': '最高采购价',
  'order.issue.classify': '取消分类', 'return.decision.suggest': '退货决策',
  'return.pattern.analyze': '退货模式分析',
  'order.anomaly.detect': '订单异常',
  'finance.daily.commentary': '每日评述', 'finance.profit.anomaly': '利润异常',
  'finance.transaction.tag': '费用分类',
  'report.summary.generate': '报表摘要',
  'auto-pilot.prompt': '自动运营 Prompt', 'autopilot.config.suggest': '自动运营配置',
  'product.image.generate': '图片生成',
  'agent.planner': '计划生成',
  'translate.text': '文本翻译',
  'marketing.campaign.analyze': '广告分析',
  'service.reply.suggest': '回复建议', 'service.question.answer': '问答回复', 'service.review.analyze': '评价分析',
  'operations.replenish.suggest': '补货建议', 'operations.trend.commentary': '趋势评述',
  'pricing.competitive.analyze': '竞争定价',
  'draft.quality.check': '草稿质检', 'draft.auto.correct': '草稿修正',
}

const SIDEBAR_ITEMS = [
  { key: 'providers', label: 'LLM 提供商', icon: <ApiOutlined /> },
  { key: 'ai-config', label: 'AI 模型配置', icon: <RobotOutlined /> },
  { key: 'auto-pilot', label: '自动运营', icon: <ThunderboltOutlined /> },
  { key: 'shops', label: '店铺管理', icon: <ShopOutlined /> },
  { key: 'notifications', label: '通知渠道', icon: <BellOutlined /> },
]

// ──────────────────────────── Component ────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('providers')

  // ── Provider state ──
  const [providers, setProviders] = useState<ProviderItem[]>([])
  const [providerLoading, setProviderLoading] = useState(false)
  const [providerModalOpen, setProviderModalOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<ProviderItem | null>(null)
  const [providerForm] = Form.useForm()
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { success: boolean; message: string; time: string }>>({})
  const [builtinSet] = useState<Set<string>>(new Set())

  // ── Shop state ──
  const [shops, setShops] = useState<ShopItem[]>([])
  const [shopLoading, setShopLoading] = useState(false)
  const [shopModalOpen, setShopModalOpen] = useState(false)
  const [editingShop, setEditingShop] = useState<ShopItem | null>(null)
  const [shopForm] = Form.useForm()
  const [testingShopId, setTestingShopId] = useState<string | null>(null)

  // ── Notification state ──
  const [notifyData, setNotifyData] = useState<NotifyChannelsData | null>(null)

  // ── AI model config state ──
  const [aiConfig, setAiConfig] = useState<any>({ tiers: {}, features: {} })
  const [aiConfigLoading, setAiConfigLoading] = useState(false)
  const [providerMap, setProviderMap] = useState<Record<string, string>>({})
  const [aiEditModalOpen, setAiEditModalOpen] = useState(false)
  const [aiEditMode, setAiEditMode] = useState<'tier' | 'feature'>('tier')
  const [aiEditKey, setAiEditKey] = useState<string>('')
  const [aiEditData, setAiEditData] = useState<any>({})
  const [aiEditForm] = Form.useForm()

  // ── Auto-pilot state ──
  const [apPromptText, setApPromptText] = useState('')
  const [apPromptLoading, setApPromptLoading] = useState(false)
  const [apSaving, setApSaving] = useState(false)
  const [apGenDesc, setApGenDesc] = useState('')
  const [apGenLoading, setApGenLoading] = useState(false)
  const [apGenResult, setApGenResult] = useState('')
  const [apSelectedShop, setApSelectedShop] = useState('')

  // ───────────────────────── API Loaders ─────────────────────────

  const loadProviders = useCallback(async () => {
    setProviderLoading(true)
    try {
      const { data } = await client.get('/api/providers')
      const items: ProviderItem[] = Object.entries(data.providers || {}).map(
        ([id, p]: [string, any]) => ({ id, ...p }),
      )
      builtinSet.clear()
      ;(data.builtin || []).forEach((id: string) => builtinSet.add(id))
      setProviders(items)
    } catch (err: any) {
      message.error('加载 LLM 提供商失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setProviderLoading(false)
    }
  }, [])

  const loadShops = useCallback(async () => {
    setShopLoading(true)
    try {
      const { data } = await client.get('/api/shops')
      setShops(data.shops || [])
    } catch (err: any) {
      message.error('加载店铺列表失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setShopLoading(false)
    }
  }, [])

  const loadChannels = useCallback(async () => {
    try {
      const { data } = await client.get('/api/notifications/channels')
      setNotifyData(data)
    } catch { /* silent */ }
  }, [])

  const loadAiConfig = useCallback(async () => {
    setAiConfigLoading(true)
    try {
      const { data } = await client.get('/api/ai-model-config')
      setAiConfig(data)
    } catch (err: any) {
      message.error('加载 AI 模型配置失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setAiConfigLoading(false)
    }
  }, [])

  useEffect(() => {
    loadProviders()
    loadShops()
    loadChannels()
    loadAiConfig()
  }, [])

  useEffect(() => {
    if (providers.length > 0) {
      const pmap: Record<string, string> = {}
      for (const p of providers) pmap[p.id] = p.default_model
      setProviderMap(pmap)
    }
  }, [providers])

  // ───────────────────── Provider Handlers ─────────────────────

  const openAddProvider = () => {
    setEditingProvider(null)
    providerForm.resetFields()
    setProviderModalOpen(true)
  }

  const openEditProvider = (p: ProviderItem) => {
    setEditingProvider(p)
    providerForm.setFieldsValue({
      name: p.name,
      default_model: p.default_model,
      base_url: p.base_url,
      api_key: '',
      doc: p.doc,
      context_length: p.context_length,
    })
    setProviderModalOpen(true)
  }

  const handleProviderSubmit = async () => {
    try {
      const values = await providerForm.validateFields()
      if (editingProvider) {
        const body: Record<string, any> = {}
        if (values.name !== undefined) body.name = values.name
        if (values.default_model !== undefined) body.default_model = values.default_model
        if (values.base_url !== undefined) body.base_url = values.base_url
        // Explicitly read api_key from form to avoid password field quirks
        const apiKey = providerForm.getFieldValue('api_key')
        if (apiKey) body.api_key = apiKey
        if (values.doc !== undefined) body.doc = values.doc
        if (values.context_length !== undefined) body.context_length = Number(values.context_length)
        await client.put(`/api/providers/${editingProvider.id}`, body)
        message.success('提供商已更新')
      } else {
        await client.post('/api/providers', {
          id: values.id,
          name: values.name,
          transport: values.transport,
          api_key: values.api_key || '',
          base_url: values.base_url || '',
          default_model: values.default_model || '',
          doc: values.doc || '',
          context_length: Number(values.context_length) || 200000,
        })
        message.success('提供商已添加')
      }
      setProviderModalOpen(false)
      loadProviders()
    } catch (err: any) {
      if (err?.errorFields) return
      message.error('操作失败: ' + (err?.response?.data?.detail || err.message))
    }
  }

  const handleDeleteProvider = async (id: string) => {
    try {
      await client.delete(`/api/providers/${id}`)
      message.success('提供商已重置')
      loadProviders()
    } catch (err: any) {
      message.error('重置失败: ' + (err?.response?.data?.detail || err.message))
    }
  }

  const handleTestProvider = async (id: string) => {
    setTestingProviderId(id)
    try {
      const { data } = await client.post(`/api/providers/${id}/test`)
      if (data.success) {
        setTestResults(prev => ({
          ...prev,
          [id]: { success: true, message: `连接成功 · 模型: ${data.model}`, time: new Date().toLocaleString('zh-CN') },
        }))
      } else {
        setTestResults(prev => ({
          ...prev,
          [id]: { success: false, message: data.error || '连接失败', time: new Date().toLocaleString('zh-CN') },
        }))
      }
    } catch (err: any) {
      setTestResults(prev => ({
        ...prev,
        [id]: { success: false, message: err?.response?.data?.detail || err.message, time: new Date().toLocaleString('zh-CN') },
      }))
    } finally {
      setTestingProviderId(null)
    }
  }

  // ────────────────────── Shop Handlers ──────────────────────

  const openAddShop = () => {
    setEditingShop(null)
    shopForm.resetFields()
    setShopModalOpen(true)
  }

  const openEditShop = (s: ShopItem) => {
    setEditingShop(s)
    shopForm.setFieldsValue({
      name: s.name,
      client_id: s.client_id,
      api_key: '',
      status: s.status,
      sync_days: s.sync_days ?? 90,
    })
    setShopModalOpen(true)
  }

  const handleShopSubmit = async () => {
    try {
      const values = await shopForm.validateFields()
      if (editingShop) {
        const body: Record<string, any> = {}
        if (values.name !== undefined) body.name = values.name
        if (values.client_id !== undefined) body.client_id = values.client_id
        if (values.api_key) body.api_key = values.api_key
        if (values.status !== undefined) body.status = values.status
        if (values.sync_days !== undefined) body.sync_days = Number(values.sync_days)
        await client.patch(`/api/shops/${editingShop.shop_id}`, body)
        message.success('店铺已更新')
      } else {
        await client.post('/api/shops', {
          shop_id: values.shop_id,
          name: values.name,
          client_id: values.client_id,
          api_key: values.api_key,
          token: values.token || '',
          sync_days: values.sync_days ?? 90,
        })
        message.success('店铺已添加')
      }
      setShopModalOpen(false)
      loadShops()
    } catch (err: any) {
      if (err?.errorFields) return
      message.error('操作失败: ' + (err?.response?.data?.detail || err.message))
    }
  }

  const handleDeleteShop = async (id: string) => {
    try {
      await client.delete(`/api/shops/${id}`)
      message.success('店铺已删除')
      loadShops()
    } catch (err: any) {
      message.error('删除失败: ' + (err?.response?.data?.detail || err.message))
    }
  }

  const handleTestShop = async (id: string) => {
    setTestingShopId(id)
    try {
      const { data } = await client.post(`/api/shops/${id}/authenticate`)
      if (data.success) {
        message.success('连接测试成功')
      } else {
        message.error('连接测试失败')
      }
    } catch (err: any) {
      message.error('连接测试失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setTestingShopId(null)
    }
  }

  // ────────────────────── AI Config Handlers ──────────────────────

  const buildFeatureList = () => {
    const tiers = aiConfig.tiers || {}
    const features = aiConfig.features || {}
    const list: any[] = []
    for (const [key, cfg] of Object.entries(features) as [string, any][]) {
      const module = key.split('.')[0]
      const tierId = cfg.tier || 'default'
      const tierCfg = tiers[tierId] || tiers.default || {}
      list.push({
        key, module: MODULE_LABELS[module] || module,
        label: FEATURE_LABELS[key] || key,
        tier: tierId,
        provider: cfg.provider || tierCfg.provider || '',
        model: cfg.model || tierCfg.model || '',
        temperature: cfg.temperature ?? tierCfg.temperature ?? '',
        max_tokens: cfg.max_tokens ?? tierCfg.max_tokens ?? '',
      })
    }
    return list
  }

  const openAiEdit = (mode: 'tier' | 'feature', key: string, data: any) => {
    setAiEditMode(mode)
    setAiEditKey(key)
    setAiEditData(data)
    aiEditForm.setFieldsValue({
      provider: data.provider || '',
      model: data.model || '',
      temperature: data.temperature ?? 0.3,
      max_tokens: data.max_tokens || 2048,
      tier: data.tier || 'default',
    })
    setAiEditModalOpen(true)
  }

  const handleAiEditSave = async () => {
    try {
      const values = await aiEditForm.validateFields()
      const updated = JSON.parse(JSON.stringify(aiConfig))
      if (aiEditMode === 'tier') {
        if (!updated.tiers[aiEditKey]) updated.tiers[aiEditKey] = {}
        updated.tiers[aiEditKey].provider = values.provider
        updated.tiers[aiEditKey].model = values.model
        updated.tiers[aiEditKey].temperature = Number(values.temperature)
        updated.tiers[aiEditKey].max_tokens = Number(values.max_tokens)
      } else {
        if (!updated.features[aiEditKey]) updated.features[aiEditKey] = {}
        updated.features[aiEditKey].tier = values.tier
        const tierCfg = updated.tiers[values.tier] || updated.tiers.default || {}
        if (values.provider && values.provider !== tierCfg.provider) {
          updated.features[aiEditKey].provider = values.provider
        } else {
          delete updated.features[aiEditKey].provider
        }
        if (values.model && values.model !== tierCfg.model) {
          updated.features[aiEditKey].model = values.model
        } else {
          delete updated.features[aiEditKey].model
        }
        if (Number(values.temperature) !== tierCfg.temperature) {
          updated.features[aiEditKey].temperature = Number(values.temperature)
        } else {
          delete updated.features[aiEditKey].temperature
        }
        if (Number(values.max_tokens) !== tierCfg.max_tokens) {
          updated.features[aiEditKey].max_tokens = Number(values.max_tokens)
        } else {
          delete updated.features[aiEditKey].max_tokens
        }
      }
      await client.put('/api/ai-model-config', updated)
      setAiConfig(updated)
      setAiEditModalOpen(false)
      message.success('AI 模型配置已更新')
    } catch (err: any) {
      if (err?.errorFields) return
      message.error('保存失败: ' + (err?.response?.data?.detail || err.message))
    }
  }

  // ── Auto-pilot: init shop selector when shops load ──
  useEffect(() => {
    if (!apSelectedShop && shops.length > 0) {
      setApSelectedShop(shops[0].shop_id)
    }
  }, [shops, apSelectedShop])

  // ── Auto-pilot: load prompt when shop changes ──
  useEffect(() => {
    if (!apSelectedShop) {
      setApPromptText('')
      return
    }
    setApPromptLoading(true)
    client.get(`/api/auto-pilot/prompt/${apSelectedShop}`)
      .then((res) => setApPromptText(res.data.prompt || ''))
      .catch(() => {})
      .finally(() => setApPromptLoading(false))
  }, [apSelectedShop])

  // ── Auto-pilot handlers ──
  const handleApSavePrompt = async () => {
    const shopId = apSelectedShop || shops[0]?.shop_id
    if (!shopId) return
    setApSaving(true)
    try {
      await client.put(`/api/auto-pilot/prompt/${shopId}`, { prompt_template: apPromptText })
      message.success('自动运营 prompt 已保存')
    } catch (err: any) {
      message.error('保存失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setApSaving(false)
    }
  }

  const handleApGenerate = async () => {
    if (!apGenDesc.trim()) return
    const shopId = apSelectedShop || shops[0]?.shop_id
    if (!shopId) return
    setApGenLoading(true)
    setApGenResult('')
    try {
      const { data } = await client.post('/api/auto-pilot/prompt/generate', {
        shop_id: shopId, description: apGenDesc,
      })
      setApGenResult(data.prompt || '')
      setApPromptText(data.prompt || '')
      message.success('Prompt 生成成功')
      setApGenDesc('')
    } catch (err: any) {
      message.error('生成失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setApGenLoading(false)
    }
  }

  const handleApSaveGenerated = async () => {
    if (!apGenResult) return
    const shopId = apSelectedShop || shops[0]?.shop_id
    if (!shopId) return
    setApSaving(true)
    try {
      await client.put(`/api/auto-pilot/prompt/${shopId}`, { prompt_template: apGenResult })
      message.success('已保存生成的 prompt')
    } catch (err: any) {
      message.error('保存失败: ' + (err?.response?.data?.detail || err.message))
    } finally {
      setApSaving(false)
    }
  }

  // ────────────────────── Utility ──────────────────────

  const maskKey = (key: string) => {
    if (!key) return ''
    if (key.length <= 6) return key.substring(0, 2) + '****'
    return key.substring(0, 6) + '****' + key.substring(key.length - 4)
  }

  const maskClientId = (id: string) => {
    if (!id) return ''
    if (id.length <= 4) return '****'
    return id.substring(0, 2) + '****' + id.substring(id.length - 2)
  }

  const getProviderStatus = (p: ProviderItem) => {
    if (!p.has_api_key) return 'offline'
    const test = testResults[p.id]
    if (test && !test.success) return 'error'
    return 'online'
  }

  const providerOnlineCount = providers.filter(p => p.has_api_key).length

  // ══════════════════ Render: Provider Section ══════════════════

  const renderProviders = () => (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          配置 AI 模型提供商，支持 OpenAI / Anthropic 等协议兼容的服务
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAddProvider}>
          添加 Provider
        </Button>
      </div>

      {providers.length === 0 && !providerLoading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          <ApiOutlined style={{ fontSize: 40, marginBottom: 12 }} />
          <div>暂无 Provider，点击上方按钮添加</div>
        </div>
      ) : (
        <Row gutter={[16, 16]}>
          {providers.map((p) => {
            const testResult = testResults[p.id]
            return (
              <Col key={p.id} xs={24} sm={12} lg={8}>
                <Card
                  loading={providerLoading}
                  size="small"
                  title={
                    <Space>
                      <ApiOutlined />
                      <Text strong>{p.name}</Text>
                      {builtinSet.has(p.id) && <Tag color="blue" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>内置</Tag>}
                    </Space>
                  }
                  extra={
                    <StatusTag
                      status={getProviderStatus(p)}
                      label={p.has_api_key ? '在线' : '离线'}
                    />
                  }
                  actions={[
                    <Tooltip title="测试连接" key="test">
                      <Button
                        type="link" size="small" icon={<ReloadOutlined />}
                        loading={testingProviderId === p.id}
                        onClick={() => handleTestProvider(p.id)}
                      />
                    </Tooltip>,
                    <Tooltip title="编辑" key="edit">
                      <Button type="link" size="small" icon={<EditOutlined />}
                        onClick={() => openEditProvider(p)}
                      />
                    </Tooltip>,
                    <Popconfirm
                      title={builtinSet.has(p.id) ? '重置此提供商为默认配置？' : '确定删除此提供商？'}
                      key="delete"
                      onConfirm={() => handleDeleteProvider(p.id)}
                      okText={builtinSet.has(p.id) ? '重置' : '删除'}
                      cancelText="取消"
                    >
                      <Tooltip title={builtinSet.has(p.id) ? '重置' : '删除'}>
                        <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                      </Tooltip>
                    </Popconfirm>,
                  ]}
                >
                  <Descriptions column={1} size="small" style={{ marginTop: -8 }}>
                    <Descriptions.Item label="模型">
                      <Text code style={{ fontSize: 12 }}>{p.default_model || '—'}</Text>
                    </Descriptions.Item>
                    <Descriptions.Item label="Base URL">
                      {p.base_url ? (
                        <Tooltip title={p.base_url}>
                          <Text copyable={{ text: p.base_url }} style={{ fontSize: 12, maxWidth: 180 }} ellipsis>
                            {p.base_url}
                          </Text>
                        </Tooltip>
                      ) : <Text type="secondary">—</Text>}
                    </Descriptions.Item>
                    <Descriptions.Item label="API Key">
                      <Space size={4}>
                        {p.has_api_key ? (
                          <>
                            <Text code style={{ fontSize: 12 }}>
                              {p.api_key ? maskKey(p.api_key) : '••••••••'}
                            </Text>
                            <Tag color={p.api_key ? 'green' : 'blue'} style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>
                              {p.api_key ? '已保存' : '环境变量'}
                            </Tag>
                          </>
                        ) : (
                          <Tag color="default" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>未配置</Tag>
                        )}
                      </Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="上下文">
                      {p.context_length?.toLocaleString() || '—'} tokens
                    </Descriptions.Item>
                  </Descriptions>

                  {/* Inline test result */}
                  {testResult && (
                    <div style={{
                      marginTop: 8, padding: '6px 10px', borderRadius: 6,
                      background: testResult.success ? '#f6ffed' : '#fff2f0',
                      fontSize: 12, color: testResult.success ? '#52c41a' : '#ff4d4f',
                    }}>
                      {testResult.success ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                      <span style={{ marginLeft: 6 }}>{testResult.message}</span>
                      <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>{testResult.time}</div>
                    </div>
                  )}
                </Card>
              </Col>
            )
          })}
        </Row>
      )}
    </div>
  )

  // ══════════════════ Render: AI Config Section ══════════════════

  const renderAiConfig = () => {
    const tierData = Object.entries(aiConfig.tiers || {}).map(([k, v]: [string, any]) => ({ id: k, ...v }))
    const featureData = buildFeatureList()

    return (
      <div>
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 13 }}>
            配置各 AI 功能使用的模型层级和参数。每个 AI 功能 → 分配到层级 → 使用该层级的 Provider/模型
          </Text>
        </div>

        {/* Tier table */}
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>
          模型层级 <Tag style={{ marginLeft: 6 }}>{tierData.length}</Tag>
        </Text>
        <Table
          dataSource={tierData}
          columns={[
            { title: '层级', dataIndex: 'id', key: 'id', width: 100 },
            { title: 'Provider', dataIndex: 'provider', key: 'provider', width: 120 },
            { title: '模型', dataIndex: 'model', key: 'model', width: 200 },
            { title: '温度', dataIndex: 'temperature', key: 'temperature', width: 80 },
            { title: 'Max Tokens', dataIndex: 'max_tokens', key: 'max_tokens', width: 110,
              render: (v: number) => v?.toLocaleString() ?? '—',
            },
            {
              title: '操作', key: 'actions', width: 60,
              render: (_: any, r: any) => (
                <Button type="link" size="small" icon={<EditOutlined />}
                  onClick={() => openAiEdit('tier', r.id, r)}
                />
              ),
            },
          ]}
          rowKey="id"
          loading={aiConfigLoading}
          pagination={false}
          size="small"
          bordered
          style={{ background: '#fff', marginBottom: 24 }}
        />

        {/* Feature table */}
        <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>
          AI 功能映射 <Tag style={{ marginLeft: 6 }}>{featureData.length}</Tag>
        </Text>
        <Table
          dataSource={featureData}
          columns={[
            { title: '模块', dataIndex: 'module', key: 'module', width: 70,
              render: (v: string, _: any, idx: number) => {
                const prev = idx > 0 ? featureData[idx - 1]?.module : null
                return v !== prev ? <Tag color="default">{v}</Tag> : null
              },
            },
            { title: 'AI 功能', dataIndex: 'label', key: 'label', width: 160 },
            { title: '层级', dataIndex: 'tier', key: 'tier', width: 80,
              render: (v: string) => <Tag color="blue">{v}</Tag>,
            },
            { title: 'Provider', dataIndex: 'provider', key: 'provider', width: 100 },
            { title: '模型', dataIndex: 'model', key: 'model', width: 200 },
            { title: '温度', dataIndex: 'temperature', key: 'temperature', width: 70 },
            { title: 'Max Tokens', dataIndex: 'max_tokens', key: 'max_tokens', width: 90 },
            {
              title: '操作', key: 'actions', width: 60,
              render: (_: any, r: any) => (
                <Button type="link" size="small" icon={<EditOutlined />}
                  onClick={() => openAiEdit('feature', r.key, r)}
                />
              ),
            },
          ]}
          rowKey="key"
          loading={aiConfigLoading}
          pagination={false}
          size="small"
          bordered
          style={{ background: '#fff' }}
        />
      </div>
    )
  }

  // ══════════════════ Render: Shops Section ══════════════════

  const renderShops = () => (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          Ozon 店铺配置，每个店铺需要独立的 Client ID 和 API Key
        </Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAddShop}>
          添加店铺
        </Button>
      </div>

      {shops.length === 0 && !shopLoading ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          <ShopOutlined style={{ fontSize: 40, marginBottom: 12 }} />
          <div>暂无店铺，点击上方按钮添加</div>
        </div>
      ) : (
        <Row gutter={[16, 16]}>
          {shops.map((shop) => (
            <Col key={shop.shop_id} xs={24} sm={12} lg={8} xl={6}>
              <Card
                loading={shopLoading}
                size="small"
                title={
                  <Space>
                    <ShopOutlined />
                    {shop.name && <Text strong>{shop.name}</Text>}
                    <StatusTag status={shop.status || 'active'} />
                  </Space>
                }
                actions={[
                  <Tooltip title="测试连接" key="test">
                    <Button type="link" size="small" icon={<ReloadOutlined />}
                      loading={testingShopId === shop.shop_id}
                      onClick={() => handleTestShop(shop.shop_id)}
                    />
                  </Tooltip>,
                  <Tooltip title="编辑" key="edit">
                    <Button type="link" size="small" icon={<EditOutlined />}
                      onClick={() => openEditShop(shop)}
                    />
                  </Tooltip>,
                  <Popconfirm title="确定删除此店铺？" key="delete"
                    onConfirm={() => handleDeleteShop(shop.shop_id)}
                    okText="删除" cancelText="取消"
                  >
                    <Tooltip title="删除">
                      <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                    </Tooltip>
                  </Popconfirm>,
                ]}
              >
                <Descriptions column={1} size="small" style={{ marginTop: -8 }}>
                  <Descriptions.Item label="店铺 ID">
                    <Text copyable={{ text: shop.shop_id }} style={{ fontSize: 12 }}>{shop.shop_id}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Client ID">
                    <Text code style={{ fontSize: 12 }}>
                      {maskClientId(shop.client_id || '') || <Text type="secondary">未配置</Text>}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="状态">
                    <StatusTag status={shop.status || 'active'} />
                  </Descriptions.Item>
                  <Descriptions.Item label="同步天数">
                    {shop.sync_days ?? 90} 天
                  </Descriptions.Item>
                  <Descriptions.Item label="创建时间">
                    {shop.created_at ? new Date(shop.created_at).toLocaleDateString('zh-CN') : <Text type="secondary">—</Text>}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </div>
  )

  // ══════════════════ Render: Notifications Section ══════════════════

  const renderNotifications = () => (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          配置外部通知渠道，Agent 可通过这些渠道发送运营通知和告警
        </Text>
      </div>

      {!notifyData ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#bbb' }}>
          <BellOutlined style={{ fontSize: 40, marginBottom: 12 }} />
          <div>通知服务未就绪</div>
        </div>
      ) : (
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={8}>
            <Card
              title={
                <Space>
                  <span>飞书 (Feishu)</span>
                  {notifyData?.ready ? <StatusTag status="online" /> : <StatusTag status="offline" />}
                </Space>
              }
              size="small"
            >
              {notifyData?.channels &&
              Object.values(notifyData.channels).some((c: any) => c.platform === 'feishu') ? (
                <Descriptions column={1} size="small">
                  {Object.entries(notifyData.channels)
                    .filter(([, c]: [string, any]) => c.platform === 'feishu')
                    .map(([key, ch]: [string, any]) => (
                      <div key={key}>
                        <Descriptions.Item label="频道">{ch.name || ch.chat_id || key}</Descriptions.Item>
                        <Descriptions.Item label="Chat ID">
                          <Text code style={{ fontSize: 12 }}>{ch.chat_id || '—'}</Text>
                        </Descriptions.Item>
                      </div>
                    ))}
                </Descriptions>
              ) : (
                <div style={{ color: '#999', fontSize: 13, marginBottom: 12 }}>
                  尚未配置飞书机器人
                </div>
              )}
              <Button icon={<PlusOutlined />} block style={{ marginTop: notifyData?.channels ? 12 : 0 }}
                onClick={() => message.info('飞书接入流程将在后续版本开放')}
              >
                {notifyData?.channels && Object.values(notifyData.channels).some((c: any) => c.platform === 'feishu')
                  ? '重新连接' : '连接飞书'}
              </Button>
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={8}>
            <Card title="可用平台" size="small">
              {notifyData?.available_platforms && notifyData.available_platforms.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 2.2 }}>
                  {notifyData.available_platforms.map((pf) => (
                    <li key={pf}><Text style={{ fontSize: 13 }}>{pf}</Text></li>
                  ))}
                </ul>
              ) : (
                <Text type="secondary" style={{ fontSize: 13 }}>暂无可用平台</Text>
              )}
            </Card>
          </Col>
        </Row>
      )}
    </div>
  )

  // ══════════════════ Render: Auto-Pilot Section ══════════════════

  const renderAutoPilot = () => (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          配置自动运营 prompt 模板。该 prompt 将在 Agent 页面点击「自动运营」按钮时发送给 AI Agent。
        </Text>
      </div>

      {/* Shop selector */}
      {shops.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Space>
            <Text>选择店铺：</Text>
            <Select
              value={apSelectedShop}
              onChange={(val) => setApSelectedShop(val)}
              options={shops.map(s => ({ value: s.shop_id, label: s.name || s.shop_id }))}
              style={{ width: 240 }}
            />
          </Space>
        </div>
      )}

      {/* ── Prompt Template Editor ── */}
      <Card size="small" title="Prompt 模板" style={{ marginBottom: 16 }}>
        <Input.TextArea
          value={apPromptText}
          onChange={(e) => setApPromptText(e.target.value)}
          rows={6}
          placeholder="输入自动运营 prompt 模板..."
          style={{ marginBottom: 12 }}
        />
        <Button type="primary" icon={<SaveOutlined />} loading={apSaving} onClick={handleApSavePrompt}>
          保存 Prompt
        </Button>
        <Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
          使用 {'{shop_id}'} 作为店铺 ID 占位符
        </Text>
      </Card>

      {/* ── LLM Prompt Generator ── */}
      <Card size="small" title="从描述生成 Prompt" style={{ marginBottom: 16 }}>
        <Input.TextArea
          value={apGenDesc}
          onChange={(e) => setApGenDesc(e.target.value)}
          rows={3}
          placeholder="用自然语言描述你的运营需求，例如：每天检查订单和库存，如果有异常就通知我..."
          style={{ marginBottom: 12 }}
        />
        <Button icon={<RobotOutlined />} loading={apGenLoading} onClick={handleApGenerate}>
          生成 Prompt
        </Button>
        {apGenResult && (
          <div style={{ marginTop: 12 }}>
            <Text strong style={{ display: 'block', marginBottom: 4 }}>生成结果：</Text>
            <div style={{
              background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6,
              padding: '10px 14px', marginBottom: 8, whiteSpace: 'pre-wrap', fontSize: 13,
            }}>
              {apGenResult}
            </div>
            <Button icon={<SaveOutlined />} loading={apSaving} onClick={handleApSaveGenerated}>
              保存生成的 Prompt
            </Button>
          </div>
        )}
      </Card>
    </div>
  )

  // ══════════════════ Content Router ══════════════════

  const renderContent = () => {
    switch (activeTab) {
      case 'providers': return renderProviders()
      case 'ai-config': return renderAiConfig()
      case 'auto-pilot': return renderAutoPilot()
      case 'shops': return renderShops()
      case 'notifications': return renderNotifications()
      default: return renderProviders()
    }
  }

  // ══════════════════ Main Render ══════════════════

  return (
    <Layout style={{ height: '100%', background: '#fff' }}>
      <Sider
        width={160}
        style={{
          background: '#fafafa',
          borderRight: '1px solid #f0f0f0',
          overflow: 'auto',
        }}
      >
        <div style={{ padding: '16px 16px 8px' }}>
          <Text strong style={{ fontSize: 15 }}>系统设置</Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[activeTab]}
          onSelect={({ key }) => setActiveTab(key)}
          items={SIDEBAR_ITEMS.map(item => ({
            key: item.key,
            icon: item.icon,
            label: item.key === 'providers'
              ? <span>{item.label} <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>{providerOnlineCount}/{providers.length}</Tag></span>
              : item.label,
          }))}
          style={{ background: 'transparent', borderRight: 'none', fontSize: 13 }}
        />
      </Sider>

      <Content key={activeTab} style={{ padding: 24, overflow: 'auto', background: '#f5f5f5' }}>
        <PageHeader
          title={SIDEBAR_ITEMS.find(i => i.key === activeTab)?.label || '系统设置'}
          subtitle={activeTab === 'providers' ? '管理 LLM 提供商和 API Key' :
                    activeTab === 'ai-config' ? '配置 AI 功能使用的模型层级' :
                    activeTab === 'auto-pilot' ? '配置自动运营 Prompt 模板' :
                    activeTab === 'shops' ? '管理 Ozon 店铺' : '配置通知渠道'}
        />
        {renderContent()}
      </Content>

      {/* ═══════════════════ Provider Modal ═══════════════════ */}
      <Modal
        title={editingProvider ? '编辑 LLM 提供商' : '添加 LLM 提供商'}
        open={providerModalOpen}
        onOk={handleProviderSubmit}
        onCancel={() => setProviderModalOpen(false)}
        width={520}
        destroyOnClose
      >
        <Form form={providerForm} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入提供商名称' }]}>
            <Input placeholder="如 DeepSeek" />
          </Form.Item>

          {!editingProvider ? (
            <>
              <Form.Item name="id" label="标识 (ID)" rules={[{ required: true, message: '请输入 Provider ID' }]}>
                <Input placeholder="如 my-custom-provider" />
              </Form.Item>
              <Form.Item name="transport" label="传输协议" rules={[{ required: true, message: '请选择传输协议' }]}>
                <Select options={[
                  { value: 'openai', label: 'OpenAI 兼容' },
                  { value: 'anthropic', label: 'Anthropic 兼容' },
                ]} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item label="标识 (ID)">
                <Text code>{editingProvider.id}</Text>
              </Form.Item>
              <Form.Item label="传输协议">
                <Tag color="blue">{editingProvider.transport === 'openai' ? 'OpenAI 兼容' : 'Anthropic 兼容'}</Tag>
              </Form.Item>
            </>
          )}

          <Form.Item name="default_model" label="默认模型">
            <Input placeholder="如 deepseek-v4-flash" />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL">
            <Input placeholder="https://api.deepseek.com/v1" />
          </Form.Item>

          {/* API Key with status */}
          <Form.Item
            name="api_key"
            label={editingProvider ? 'API Key（留空不变）' : 'API Key'}
          >
            <Input.Password
              placeholder={editingProvider ? '留空则保持现有值' : 'sk-...'}
              autoComplete="new-password"
            />
          </Form.Item>
          {editingProvider && (
            <div style={{ marginTop: -16, marginBottom: 16 }}>
              <Space size={8}>
                <Text type="secondary" style={{ fontSize: 12 }}>当前状态: </Text>
                {editingProvider.has_api_key ? (
                  <>
                    <Tag color="green" icon={<KeyOutlined />}>API Key 已配置</Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {editingProvider.api_key ? '来自已保存的密钥' : `来自环境变量 ${editingProvider.api_key_env}`}
                    </Text>
                  </>
                ) : (
                  <Tag color="default">未配置</Tag>
                )}
              </Space>
            </div>
          )}

          <Form.Item name="context_length" label="上下文长度" initialValue={200000}>
            <Input type="number" min={1000} />
          </Form.Item>
          <Form.Item name="doc" label="描述">
            <Input.TextArea rows={2} placeholder="可选，关于此提供商的说明" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ═══════════════════ Shop Modal ═══════════════════ */}
      <Modal
        title={editingShop ? '编辑店铺' : '添加店铺'}
        open={shopModalOpen}
        onOk={handleShopSubmit}
        onCancel={() => setShopModalOpen(false)}
        width={520}
        destroyOnClose
      >
        <Form form={shopForm} layout="vertical" style={{ marginTop: 8 }}>
          {!editingShop && (
            <Form.Item name="shop_id" label="店铺 ID" rules={[{ required: true, message: '请输入店铺 ID' }]}>
              <Input placeholder="唯一标识，如 shop-1" />
            </Form.Item>
          )}
          <Form.Item name="name" label="店铺名称" rules={[{ required: true, message: '请输入店铺名称' }]}>
            <Input placeholder="如 我的 Ozon 店铺" />
          </Form.Item>
          <Form.Item name="client_id" label="Ozon Client ID" rules={[{ required: true, message: '请输入 Ozon Client ID' }]}>
            <Input placeholder="从 Ozon Seller API 获取" />
          </Form.Item>
          <Form.Item name="api_key" label={editingShop ? 'API Key（留空不变）' : 'API Key'}
            rules={editingShop ? [] : [{ required: true, message: '请输入 Ozon API Key' }]}
          >
            <Input.Password placeholder={editingShop ? '留空则保持现有值' : 'Ozon API Key'} autoComplete="off" />
          </Form.Item>
          {!editingShop && (
            <Form.Item name="token" label="Token（可选）">
              <Input placeholder="Ozon 令牌" />
            </Form.Item>
          )}
          <Form.Item name="sync_days" label="同步天数" initialValue={90}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ═══════════════════ AI Config Edit Modal ═══════════════════ */}
      <Modal
        title={aiEditMode === 'tier' ? '编辑模型层级' : '编辑 AI 功能映射'}
        open={aiEditModalOpen}
        onOk={handleAiEditSave}
        onCancel={() => setAiEditModalOpen(false)}
        width={520}
        destroyOnClose
      >
        <Form form={aiEditForm} layout="vertical" style={{ marginTop: 8 }}>
          {aiEditMode === 'feature' && (
            <Form.Item name="tier" label="模型层级" rules={[{ required: true }]}>
              <Select options={Object.keys(aiConfig.tiers || {}).map(k => ({
                value: k, label: k + (k === 'default' ? ' (默认)' : ''),
              }))} />
            </Form.Item>
          )}
          <Form.Item name="provider" label="Provider">
            <Select allowClear placeholder="使用层级默认值"
              options={Object.keys(providerMap).map(k => ({ value: k, label: k }))}
            />
          </Form.Item>
          <Form.Item name="model" label="模型">
            <Input placeholder={aiEditMode === 'tier' ? '如 deepseek-v4-flash' : '留空则使用层级默认模型'} />
          </Form.Item>
          <Form.Item name="temperature" label="温度 (Temperature)">
            <Input type="number" min={0} max={2} step={0.1} />
          </Form.Item>
          <Form.Item name="max_tokens" label="最大 Tokens">
            <Input type="number" min={1} max={32768} />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}
