import { useState } from 'react'
import {
  Card, Form, InputNumber, Select, Button, message, Tabs,
  Modal, Space, Row, Col, Descriptions, Statistic, Divider, Tag, Switch, Spin, Empty, Alert,
} from 'antd'
import {
  CalculatorOutlined, PlusOutlined, PlayCircleOutlined, PauseCircleOutlined,
  ThunderboltOutlined, DeleteOutlined, EditOutlined, ReloadOutlined, RobotOutlined,
} from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable, { type Column } from '../../components/DataTable'
import StatusTag from '../../components/StatusTag'
import ConfirmModal from '../../components/ConfirmModal'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'
import { priceSuffix } from '../../utils/currency'

/* ─────────── Types ─────────── */

interface PriceCalcResult {
  recommended_price: number
  cost_breakdown: Record<string, number>
  profit_margin: number
  currency?: string
}

interface ProfitCalcResult {
  selling_price: number
  cost_breakdown: Record<string, number>
  profit: number
  profit_margin: number
  currency?: string
}

interface PricingRule {
  id: string
  name: string
  type: 'markup' | 'discount' | 'fixed' | 'cost_plus'
  action?: string
  value: number
  priority: number
  conditions: Record<string, any>
  enabled: boolean
  created_at?: string
}

interface SchedulerStatus {
  running: boolean
  next_run: string | null
  last_run: string | null
  last_status: string | null
}

/* ─────────── Constants ─────────── */

const CATEGORY_OPTIONS = [
  { label: '电子产品', value: 'electronics' },
  { label: '服装鞋帽', value: 'clothing' },
  { label: '家居园艺', value: 'home_garden' },
  { label: '美妆个护', value: 'beauty' },
  { label: '运动户外', value: 'sports' },
  { label: '图书文具', value: 'books' },
  { label: '玩具母婴', value: 'toys' },
  { label: '食品饮料', value: 'food' },
  { label: '汽车配件', value: 'auto' },
  { label: '宠物用品', value: 'pets' },
  { label: '医疗健康', value: 'health' },
  { label: '其他', value: 'other' },
]

const WAREHOUSE_OPTIONS = [
  { label: '主仓库 (莫斯科)', value: 'main_moscow' },
  { label: '圣彼得堡仓库', value: 'spb' },
  { label: '新西伯利亚仓库', value: 'novosibirsk' },
  { label: '喀山仓库', value: 'kazan' },
  { label: '叶卡捷琳堡仓库', value: 'ekaterinburg' },
]

const DELIVERY_SPEED_OPTIONS = [
  { label: '标准 (3-5天)', value: 'standard' },
  { label: '快递 (1-2天)', value: 'express' },
  { label: '当日达', value: 'same_day' },
]

const RULE_TYPE_MAP: Record<string, { label: string; color: string }> = {
  markup: { label: '加价', color: 'blue' },
  discount: { label: '折扣', color: 'orange' },
  fixed: { label: '固定价', color: 'purple' },
  cost_plus: { label: '成本加成', color: 'green' },
}

function getRuleActionText(type: string, value: number): string {
  switch (type) {
    case 'markup': return `加价 ${value}%`
    case 'discount': return `折扣 ${value}%`
    case 'fixed': return `固定价 ¥${value}`
    case 'cost_plus': return `成本 +¥${value}`
    default: return `${value}`
  }
}

/* ══════════════════════════════════════════════════════════════
   Tab 1: Cost Calculator (成本计算器)
   ══════════════════════════════════════════════════════════════ */

function CostCalculatorTab({ currentShop }: { currentShop: string }) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [calcResult, setCalcResult] = useState<PriceCalcResult | null>(null)
  const [profitResult, setProfitResult] = useState<ProfitCalcResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleCalculate = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      setError(null)
      setCalcResult(null)
      setProfitResult(null)

      // Step 1: get recommended price
      const priceResp = await axios.post('/api/pricing-rules/calculate-price', {
        purchase_price_cny: values.purchase_price_cny,
        weight_kg: values.weight_kg,
        category_name: values.category_name,
        target_margin: values.target_margin,
        sales_model: values.sales_model,
        shop_id: currentShop || undefined,
      })
      const priceData: PriceCalcResult = priceResp.data
      setCalcResult(priceData)

      // Step 2: get detailed profit breakdown
      if (priceData.recommended_price) {
        const profitResp = await axios.post('/api/pricing-rules/calculate-profit', {
          purchase_price_cny: values.purchase_price_cny,
          weight_kg: values.weight_kg,
          category_name: values.category_name,
          selling_price: priceData.recommended_price,
          shop_id: currentShop || undefined,
        })
        setProfitResult(profitResp.data)
      }

      message.success('计算完成')
    } catch (err: any) {
      if (err?.response?.data?.detail) {
        setError(err.response.data.detail)
      } else if (err?.errorFields) {
        // form validation error, don't show extra message
      } else {
        setError('计算失败，请检查输入后重试')
      }
    } finally {
      setLoading(false)
    }
  }

  const hasResult = calcResult !== null

  return (
    <Row gutter={24}>
      {/* Form column */}
      <Col xs={24} lg={12}>
        <Card title={<><CalculatorOutlined /> 输入参数</>} size="small">
          <Form
            form={form}
            layout="vertical"
            initialValues={{
              target_margin: 20,
              sales_model: 'FBP',
              delivery_speed: 'standard',
            }}
            onFinish={handleCalculate}
          >
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  label="采购价"
                  name="purchase_price_cny"
                  rules={[{ required: true, message: '请输入采购价' }]}
                >
                  <InputNumber<number>
                    style={{ width: '100%' }}
                    min={0}
                    precision={2}
                    placeholder="请输入"
                    formatter={(value) => `¥ ${value}`}
                    parser={(value) => parseFloat(value?.replace(/¥\s?/g, '') || '0')}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  label="重量 (kg)"
                  name="weight_kg"
                  rules={[{ required: true, message: '请输入重量' }]}
                >
                  <InputNumber<number>
                    style={{ width: '100%' }}
                    min={0}
                    precision={3}
                    placeholder="请输入"
                    formatter={(value) => `${value} kg`}
                    parser={(value) => parseFloat(value?.replace(/kg\s?/g, '') || '0')}
                  />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  label="类目"
                  name="category_name"
                  rules={[{ required: true, message: '请选择类目' }]}
                >
                  <Select
                    showSearch
                    placeholder="选择或输入类目"
                    options={CATEGORY_OPTIONS}
                    mode="tags"
                    maxCount={1}
                    onChange={(val) => form.setFieldValue('category_name', val?.[0] || val)}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  label="目标毛利率"
                  name="target_margin"
                  rules={[{ required: true, message: '请输入目标毛利率' }]}
                >
                  <InputNumber<number>
                    style={{ width: '100%' }}
                    min={0}
                    max={100}
                    precision={1}
                    placeholder="20"
                    formatter={(value) => `${value}%`}
                    parser={(value) => parseFloat(value?.replace(/%\s?/g, '') || '0')}
                  />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  label="销售模式"
                  name="sales_model"
                  rules={[{ required: true, message: '请选择销售模式' }]}
                >
                  <Select
                    placeholder="选择销售模式"
                    options={[
                      { label: 'FBP (Fulfilled by Partner)', value: 'FBP' },
                      { label: 'rFBS (Retail Fulfilled by Seller)', value: 'rFBS' },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="仓库" name="warehouse">
                  <Select
                    placeholder="选择仓库"
                    allowClear
                    options={WAREHOUSE_OPTIONS}
                  />
                </Form.Item>
              </Col>
            </Row>

            <Form.Item label="配送速度" name="delivery_speed">
              <Select
                placeholder="选择配送速度"
                allowClear
                options={DELIVERY_SPEED_OPTIONS}
              />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<CalculatorOutlined />}
                  loading={loading}
                >
                  计算
                </Button>
                <Button
                  onClick={() => {
                    form.resetFields()
                    setCalcResult(null)
                    setProfitResult(null)
                    setError(null)
                  }}
                >
                  重置
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Card>
      </Col>

      {/* Result column */}
      <Col xs={24} lg={12}>
        {error && (
          <Alert
            type="error"
            message="计算失败"
            description={error}
            showIcon
            closable
            onClose={() => setError(null)}
            style={{ marginBottom: 16 }}
          />
        )}

        {!hasResult && !error && (
          <Card size="small">
            <Empty
              description="输入参数后点击「计算」查看结果"
              style={{ padding: '60px 0' }}
            />
          </Card>
        )}

        {loading && (
          <Card size="small">
            <div style={{ textAlign: 'center', padding: '60px 0' }}>
              <Spin tip="计算中..." />
            </div>
          </Card>
        )}

        {hasResult && !loading && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            {/* Recommended price */}
            <Card size="small">
              <Statistic
                title="建议售价"
                value={calcResult!.recommended_price}
                suffix={priceSuffix('RUB')}
                valueStyle={{ color: '#1677ff', fontSize: 32, fontWeight: 600 }}
              />
              <Divider />
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title="毛利率"
                    value={calcResult!.profit_margin}
                    suffix="%"
                    precision={1}
                    valueStyle={{
                      color: calcResult!.profit_margin >= 0 ? '#52c41a' : '#ff4d4f',
                    }}
                  />
                </Col>
                <Col span={12}>
                  {profitResult && (
                    <Statistic
                      title="预期利润"
                      value={profitResult.profit}
                      suffix={priceSuffix('RUB')}
                      precision={2}
                      valueStyle={{ color: '#52c41a' }}
                    />
                  )}
                </Col>
              </Row>
            </Card>

            {/* Cost breakdown */}
            <Card title="成本构成" size="small">
              <Descriptions column={1} size="small" bordered>
                {calcResult!.cost_breakdown &&
                  Object.entries(calcResult!.cost_breakdown).map(([key, val]) => (
                    <Descriptions.Item
                      key={key}
                      label={key}
                      contentStyle={{ fontFamily: 'monospace' }}
                    >
                      {typeof val === 'number' ? `${val.toFixed(2)} ${priceSuffix('RUB')}` : String(val)}
                    </Descriptions.Item>
                  ))}
                <Descriptions.Item label="总成本" contentStyle={{ fontFamily: 'monospace', fontWeight: 600 }}>
                  {calcResult!.cost_breakdown &&
                    `${Object.values(calcResult!.cost_breakdown).reduce((a, b) => a + (typeof b === 'number' ? b : 0), 0).toFixed(2)} ${priceSuffix('RUB')}`}
                </Descriptions.Item>
              </Descriptions>
            </Card>

            {/* Profit breakdown from calculate-profit */}
            {profitResult && profitResult.cost_breakdown && (
              <Card title="利润明细" size="small">
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="售价">
                    {profitResult.selling_price.toFixed(2)} {priceSuffix('RUB')}
                  </Descriptions.Item>
                  {Object.entries(profitResult.cost_breakdown).map(([key, val]) => (
                    <Descriptions.Item
                      key={key}
                      label={key}
                      contentStyle={{ fontFamily: 'monospace' }}
                    >
                      {typeof val === 'number'
                        ? `${val >= 0 ? '+' : ''}${val.toFixed(2)} ${priceSuffix('RUB')}`
                        : String(val)}
                    </Descriptions.Item>
                  ))}
                  <Descriptions.Item
                    label="净利润"
                    contentStyle={{ fontFamily: 'monospace', fontWeight: 600, color: '#52c41a' }}
                  >
                    +{profitResult.profit.toFixed(2)} {priceSuffix('RUB')}
                  </Descriptions.Item>
                  <Descriptions.Item
                    label="净利率"
                    contentStyle={{ fontWeight: 600 }}
                  >
                    {profitResult.profit_margin.toFixed(1)}%
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            )}
          </Space>
        )}
      </Col>
    </Row>
      <Modal title="AI 竞争定价分析" open={showAiPricing} onCancel={()=>setShowAiPricing(false)} footer={null} width={500}>{aiPricingResult&&<div><Tag color={aiPricingResult.current_competitiveness==='high'?'green':aiPricingResult.current_competitiveness==='medium'?'orange':'red'}>{aiPricingResult.current_competitiveness}</Tag><p style={{marginTop:8}}>最优价: {aiPricingResult.suggested_price_range?.optimal} RUB (范围: {aiPricingResult.suggested_price_range?.min}-{aiPricingResult.suggested_price_range?.max})</p>{aiPricingResult.price_adjustment_tips?.length>0&&<ul>{aiPricingResult.price_adjustment_tips.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul>}</div>}</Modal>
  )
}

/* ══════════════════════════════════════════════════════════════
   Tab 2: Pricing Rules (定价规则)
   ══════════════════════════════════════════════════════════════ */

function PricingRulesTab({ currentShop }: { currentShop: string }) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // Rule modal state
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<PricingRule | null>(null)
  const [ruleForm] = Form.useForm()
  const [saving, setSaving] = useState(false)

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<PricingRule | null>(null)

  // ── Scheduler ──

  const {
    data: schedStatus,
    isLoading: schedLoading,
    refetch: refetchSched,
  } = useQuery<SchedulerStatus>({
    queryKey: ['pricing-scheduler-status', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/pricing-rules/scheduler/status', {
        params: { shop_id: currentShop || undefined },
      })
      return data
    },
    refetchInterval: 30_000,
  })

  const startScheduler = async () => {
    try {
      await axios.post('/api/pricing-rules/scheduler/start', { shop_id: currentShop || undefined })
      message.success('调度器已启动')
      refetchSched()
    } catch {
      message.error('启动失败')
    }
  }

  const stopScheduler = async () => {
    try {
      await axios.post('/api/pricing-rules/scheduler/stop', { shop_id: currentShop || undefined })
      message.success('调度器已停止')
      refetchSched()
    } catch {
      message.error('停止失败')
    }
  }

  const runNowScheduler = async () => {
    try {
      await axios.post('/api/pricing-rules/scheduler/run-now', { shop_id: currentShop || undefined })
      message.success('已触发立即执行')
      refetchSched()
    } catch {
      message.error('触发失败')
    }
  }

  // ── Rules list ──

  const {
    data: rulesResp,
    isLoading: rulesLoading,
    refetch: refetchRules,
  } = useQuery({
    queryKey: ['pricing-rules', currentShop, page, pageSize],
    queryFn: async () => {
      const { data } = await axios.get('/api/pricing-rules', {
        params: {
          shop_id: currentShop || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        },
      })
      return data
    },
  })

  const rules: PricingRule[] = rulesResp?.rules || rulesResp?.items || []
  const rulesTotal = rulesResp?.total || rulesResp?.total_count || 0

  // ── Toggle enabled ──

  const toggleEnabled = async (rule: PricingRule) => {
    try {
      await axios.put(`/api/pricing-rules/${rule.id}`, {
        ...rule,
        enabled: !rule.enabled,
        shop_id: currentShop || undefined,
      })
      message.success(rule.enabled ? '已禁用' : '已启用')
      refetchRules()
    } catch {
      message.error('操作失败')
    }
  }

  // ── Create / Edit ──

  const openCreateModal = () => {
    setEditingRule(null)
    ruleForm.resetFields()
    ruleForm.setFieldsValue({ enabled: true, priority: 0 })
    setModalOpen(true)
  }

  const openEditModal = (rule: PricingRule) => {
    setEditingRule(rule)
    ruleForm.setFieldsValue(rule)
    setModalOpen(true)
  }

  const handleSaveRule = async () => {
    try {
      const values = await ruleForm.validateFields()
      setSaving(true)

      if (editingRule) {
        await axios.put(`/api/pricing-rules/${editingRule.id}`, {
          ...values,
          shop_id: currentShop || undefined,
        })
        message.success('规则已更新')
      } else {
        await axios.post('/api/pricing-rules', {
          ...values,
          shop_id: currentShop || undefined,
        })
        message.success('规则已创建')
      }

      setModalOpen(false)
      refetchRules()
    } catch (err: any) {
      if (err?.errorFields) return // validation error, handled by form
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  // ── Delete ──

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await axios.delete(`/api/pricing-rules/${deleteTarget.id}`, {
        params: { shop_id: currentShop || undefined },
      })
      message.success('规则已删除')
      setDeleteTarget(null)
      refetchRules()
    } catch {
      message.error('删除失败')
    }
  }

  // ── Batch apply ──

  const [applying, setApplying] = useState(false)
  const handleBatchApply = async () => {
    setApplying(true)
    try {
      await axios.post('/api/pricing-rules/apply-batch', {
        shop_id: currentShop || undefined,
      })
      message.success('批量应用已完成')
    } catch {
      message.error('批量应用失败')
    } finally {
      setApplying(false)
    }
  }

  // ── Columns ──

  const columns: Column<PricingRule>[] = [
    {
      key: 'name',
      title: '规则名称',
      dataIndex: 'name',
      width: 180,
    },
    {
      key: 'type',
      title: '类型',
      dataIndex: 'type',
      width: 100,
      render: (v: string) => {
        const cfg = RULE_TYPE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={cfg.color}>{cfg.label}</Tag>
      },
    },
    {
      key: 'action',
      title: '动作',
      width: 130,
      render: (_: any, record: PricingRule) => (
        <span>{record.action || getRuleActionText(record.type, record.value)}</span>
      ),
    },
    {
      key: 'priority',
      title: '优先级',
      dataIndex: 'priority',
      width: 80,
      sorter: (a, b) => (a.priority ?? 0) - (b.priority ?? 0),
    },
    {
      key: 'conditions',
      title: '条件',
      width: 180,
      render: (_: any, record: PricingRule) => {
        const conds = record.conditions
        if (!conds || Object.keys(conds).length === 0) {
          return <span style={{ color: '#999' }}>无限制</span>
        }
        return (
          <Space size={4} wrap>
            {Object.entries(conds).map(([k, v]) => (
              <Tag key={k} style={{ fontSize: 12 }}>
                {k}: {String(v)}
              </Tag>
            ))}
          </Space>
        )
      },
    },
    {
      key: 'enabled',
      title: '状态',
      width: 80,
      render: (_: any, record: PricingRule) => (
        <Switch
          size="small"
          checked={record.enabled}
          onChange={() => toggleEnabled(record)}
          checkedChildren="开"
          unCheckedChildren="关"
        />
      ),
    },
    {
      key: 'actions',
      title: '操作',
      width: 140,
      render: (_: any, record: PricingRule) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEditModal(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => setDeleteTarget(record)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={16}>
      {/* ── Scheduler Status Card ── */}
      <Card size="small">
        <Row align="middle" justify="space-between">
          <Col>
            <Space size={16}>
              <Space>
                <span style={{ color: '#666' }}>调度器状态：</span>
                {schedLoading ? (
                  <Spin size="small" />
                ) : (
                  <StatusTag status={schedStatus?.running ? 'running' : 'stopped'} />
                )}
              </Space>
              {schedStatus?.next_run && (
                <Space>
                  <span style={{ color: '#666' }}>下次运行：</span>
                  <span style={{ fontFamily: 'monospace' }}>
                    {new Date(schedStatus.next_run).toLocaleString('zh-CN')}
                  </span>
                </Space>
              )}
              {schedStatus?.last_run && (
                <Space>
                  <span style={{ color: '#666' }}>上次运行：</span>
                  <span style={{ fontFamily: 'monospace' }}>
                    {new Date(schedStatus.last_run).toLocaleString('zh-CN')}
                  </span>
                  {schedStatus.last_status && (
                    <Tag>{schedStatus.last_status}</Tag>
                  )}
                </Space>
              )}
            </Space>
          </Col>
          <Col>
            <Space>
              {schedStatus?.running ? (
                <Button
                  size="small"
                  icon={<PauseCircleOutlined />}
                  onClick={stopScheduler}
                >
                  停止
                </Button>
              ) : (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={startScheduler}
                >
                  启动
                </Button>
              )}
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                onClick={runNowScheduler}
              >
                立即执行
              </Button>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => { refetchSched(); refetchRules() }}
              >
                刷新
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* ── Rules Table ── */}
      <Card
        size="small"
        title="定价规则"
        extra={
          <Space>
            <Button
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              onClick={openCreateModal}
            >
              创建规则
            </Button>
            <Button
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={handleBatchApply}
              loading={applying}
            >
              批量应用
            </Button>
          </Space>
        }
      >
        <DataTable
          columns={columns}
          data={rules}
          total={rulesTotal}
          loading={rulesLoading}
          current={page}
          pageSize={pageSize}
          onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
          onRefresh={refetchRules}
          emptyText="暂无定价规则"
          rowKey="id"
        />
      </Card>

      {/* ── Create / Edit Modal ── */}
      <Modal
        title={editingRule ? '编辑规则' : '创建规则'}
        open={modalOpen}
        onOk={handleSaveRule}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        destroyOnClose
        width={520}
      >
        <Form
          form={ruleForm}
          layout="vertical"
          preserve={false}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            label="规则名称"
            name="name"
            rules={[{ required: true, message: '请输入规则名称' }]}
          >
            <input className="ant-input" placeholder="例如：电子产品加价20%" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label="规则类型"
                name="type"
                rules={[{ required: true, message: '请选择类型' }]}
              >
                <Select
                  placeholder="选择类型"
                  options={[
                    { label: '加价 (Markup)', value: 'markup' },
                    { label: '折扣 (Discount)', value: 'discount' },
                    { label: '固定价 (Fixed)', value: 'fixed' },
                    { label: '成本加成 (Cost Plus)', value: 'cost_plus' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="调整值"
                name="value"
                rules={[{ required: true, message: '请输入调整值' }]}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  precision={2}
                  placeholder="百分比或金额"
                />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="优先级" name="priority">
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  precision={0}
                  placeholder="数字越小优先级越高"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="类目过滤" name={['conditions', 'category']}>
                <Select
                  allowClear
                  placeholder="可选，选择类目"
                  options={CATEGORY_OPTIONS}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ── Delete Confirmation ── */}
      <ConfirmModal
        open={deleteTarget !== null}
        title="删除规则"
        description={`确定要删除规则「${deleteTarget?.name || ''}」吗？此操作不可撤销。`}
        danger
        confirmText="删除"
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </Space>
      <Modal title="AI 竞争定价分析" open={showAiPricing} onCancel={()=>setShowAiPricing(false)} footer={null} width={500}>{aiPricingResult&&<div><Tag color={aiPricingResult.current_competitiveness==='high'?'green':aiPricingResult.current_competitiveness==='medium'?'orange':'red'}>{aiPricingResult.current_competitiveness}</Tag><p style={{marginTop:8}}>最优价: {aiPricingResult.suggested_price_range?.optimal} RUB (范围: {aiPricingResult.suggested_price_range?.min}-{aiPricingResult.suggested_price_range?.max})</p>{aiPricingResult.price_adjustment_tips?.length>0&&<ul>{aiPricingResult.price_adjustment_tips.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul>}</div>}</Modal>
  )
}

/* ══════════════════════════════════════════════════════════════
   Main Page
   ══════════════════════════════════════════════════════════════ */

export default function Pricing() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  return (
    <div>
      <PageHeader title="定价工具"
        actions={<Space><Input placeholder="产品ID" value={aiProductId} onChange={(e)=>setAiProductId(e.target.value)} style={{width:120}}/><Tooltip title="AI 竞争定价分析"><Button size="small" icon={<RobotOutlined />} onClick={() => aiProductId && aiPricingMutation.mutate(aiProductId)} loading={aiPricingMutation.isPending}>竞争分析</Button></Tooltip></Space>} subtitle="成本计算与定价规则管理" />
      <Tabs
        items={[
          {
            key: 'calculator',
            label: '成本计算器',
            children: <CostCalculatorTab currentShop={currentShop} />,
          },
          {
            key: 'rules',
            label: '定价规则',
            children: <PricingRulesTab currentShop={currentShop} />,
          },
        ]}
      />
    </div>
      <Modal title="AI 竞争定价分析" open={showAiPricing} onCancel={()=>setShowAiPricing(false)} footer={null} width={500}>{aiPricingResult&&<div><Tag color={aiPricingResult.current_competitiveness==='high'?'green':aiPricingResult.current_competitiveness==='medium'?'orange':'red'}>{aiPricingResult.current_competitiveness}</Tag><p style={{marginTop:8}}>最优价: {aiPricingResult.suggested_price_range?.optimal} RUB (范围: {aiPricingResult.suggested_price_range?.min}-{aiPricingResult.suggested_price_range?.max})</p>{aiPricingResult.price_adjustment_tips?.length>0&&<ul>{aiPricingResult.price_adjustment_tips.map((t:string,i:number)=><li key={i}>{t}</li>)}</ul>}</div>}</Modal>
  )
}
