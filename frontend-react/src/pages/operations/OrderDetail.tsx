import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Descriptions, Tag, Button, Spin, Table, Typography, Space, InputNumber,
  Alert, Divider, message, Row, Col, Statistic, Tooltip,
} from 'antd'
import {
  ArrowLeftOutlined, RobotOutlined, DollarOutlined,
  InfoCircleOutlined, FileTextOutlined, WarningOutlined,
} from '@ant-design/icons'
import { useOutletContext } from 'react-router-dom'
import PageHeader from '../../components/PageHeader'
import StatusTag from '../../components/StatusTag'
import axios from 'axios'

const { Text, Title } = Typography

interface OrderProduct {
  name: string
  offer_id: string
  quantity: number
  price: number
  images?: string[]
  sku?: string
}

interface PurchasePriceResult {
  posting_number: string
  selling_price_cny: number
  max_purchase_price_cny: number
  max_purchase_price_rub: number
  profit_cny: number
  profit_margin_pct: number
  profitable: boolean
  cost_breakdown: {
    commission_pct: number
    commission_cny: number
    logistics_cny: number
    customs_cny: number
    return_reserve_cny: number
    packaging_cny: number
  }
  source: {
    weight_kg: number | null
    category_name: string
    weight_from: string
    category_from: string
  }
}

const CATEGORY_WEIGHT_LABELS: Record<string, string> = {
  product: '商品数据',
  estimated: '估算',
}

export default function OrderDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  const [loading, setLoading] = useState(true)
  const [order, setOrder] = useState<any>(null)
  const [orderType, setOrderType] = useState('fbo')

  // AI purchase price
  const [targetMargin, setTargetMargin] = useState(20)
  const [calcLoading, setCalcLoading] = useState(false)
  const [calcResult, setCalcResult] = useState<PurchasePriceResult | null>(null)
  const [calcError, setCalcError] = useState<string | null>(null)

  // AI anomaly detection
  const [anomalyLoading, setAnomalyLoading] = useState(false)
  const [anomalyResult, setAnomalyResult] = useState<any>(null)
  const [anomalyError, setAnomalyError] = useState<string | null>(null)

  useEffect(() => {
    if (!id || !currentShop) return
    fetchOrderDetail()
  }, [id, currentShop])

  async function fetchOrderDetail() {
    setLoading(true)
    try {
      const resp = await axios.get('/api/order-detail', {
        params: { shop_id: currentShop, posting_number: id },
      })
      setOrder(resp.data?.order || resp.data)
    } catch (e: any) {
      message.error('加载订单详情失败: ' + (e?.response?.data?.detail || e.message))
    } finally {
      setLoading(false)
    }
  }

  async function handleCalcPurchasePrice() {
    if (!id || !currentShop) return
    setCalcLoading(true)
    setCalcError(null)
    setCalcResult(null)
    try {
      const { data } = await axios.post(
        `/api/orders/${id}/ai/max-purchase-price`,
        null,
        {
          params: {
            shop_id: currentShop,
            target_margin: targetMargin,
          },
        }
      )
      setCalcResult(data)
    } catch (e: any) {
      setCalcError(e.response?.data?.detail || e.message || '计算失败')
    } finally {
      setCalcLoading(false)
    }
  }

  async function handleAnalyzeAnomaly() {
    if (!id || !currentShop) return
    setAnomalyLoading(true)
    setAnomalyError(null)
    setAnomalyResult(null)
    try {
      const { data } = await axios.post(`/api/orders/${id}/ai/analyze`, null, {
        params: { shop_id: currentShop },
      })
      setAnomalyResult(data)
    } catch (e: any) {
      setAnomalyError(e?.response?.data?.detail || e.message || '分析失败')
    } finally {
      setAnomalyLoading(false)
    }
  }

  /* ── Derive order data ── */
  const products: OrderProduct[] = order?.products || order?.product_list || []
  const totalPrice = products.reduce(
    (sum: number, p: OrderProduct) => sum + (p.price || 0) * (p.quantity || 1),
    0,
  )

  /* ── Product columns ── */
  const productColumns = [
    { key: 'offer_id', title: 'SKU', dataIndex: 'offer_id', width: 140 },
    {
      key: 'name', title: '商品名称', dataIndex: 'name', width: 260,
      render: (v: string) => v || '—',
    },
    { key: 'quantity', title: '数量', dataIndex: 'quantity', width: 60 },
    {
      key: 'price', title: '单价', dataIndex: 'price', width: 100,
      render: (v: any) => v ? `¥${Number(v).toFixed(2)}` : '—',
    },
    {
      key: 'subtotal', title: '小计', width: 100,
      render: (_: any, r: OrderProduct) => `¥${(Number(r.price || 0) * (r.quantity || 1)).toFixed(2)}`,
    },
  ]

  /* ── Cost breakdown columns ── */
  const costColumns = [
    { key: 'item', title: '费用项', dataIndex: 'item', width: 120 },
    { key: 'amount', title: '金额 (CNY)', dataIndex: 'amount', width: 120 },
    { key: 'note', title: '说明', dataIndex: 'note', width: 200 },
  ]

  const costData = calcResult
    ? [
        { key: 'commission', item: '平台佣金', amount: calcResult.cost_breakdown.commission_cny, note: `佣金率 ${calcResult.cost_breakdown.commission_pct}%` },
        { key: 'logistics', item: '物流费用', amount: calcResult.cost_breakdown.logistics_cny, note: '' },
        { key: 'customs', item: '关税', amount: calcResult.cost_breakdown.customs_cny, note: '' },
        { key: 'return_reserve', item: '退货预备金', amount: calcResult.cost_breakdown.return_reserve_cny, note: '2%' },
        { key: 'packaging', item: '包装及其他', amount: calcResult.cost_breakdown.packaging_cny, note: '' },
      ]
    : []

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <Spin size="large" tip="加载订单信息…" />
      </div>
    )
  }

  if (!order) {
    return (
      <div style={{ padding: 24 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/operations')}>返回订单列表</Button>
        <Alert style={{ marginTop: 16 }} type="error" message="未找到该订单" showIcon />
      </div>
    )
  }

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: '0 auto' }}>
      {/* Back button */}
      <Button
        icon={<ArrowLeftOutlined />}
        type="text"
        onClick={() => navigate('/operations?tab=orders')}
        style={{ marginBottom: 16, padding: 0 }}
      >
        返回订单列表
      </Button>

      {/* Order Info Card */}
      <PageHeader
        title={`订单 ${id}`}
        subtitle={`${orderType.toUpperCase()} · ${currentShop}`}
        status={{
          label: order?.status || '未知',
          color: order?.status === 'delivered' ? 'green' : order?.status === 'cancelled' ? 'red' : 'blue',
        }}
      />

      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="订单号" span={2}>
            <Text copyable>{id}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <StatusTag status={order?.status || ''} />
          </Descriptions.Item>
          <Descriptions.Item label="类型">{orderType.toUpperCase()}</Descriptions.Item>
          <Descriptions.Item label="商品数">{products.length}</Descriptions.Item>
          <Descriptions.Item label="订单金额">
            <Text strong style={{ color: '#1677FF', fontSize: 16 }}>
              ¥{totalPrice.toFixed(2)}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间" span={2}>
            {order?.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '—'}
          </Descriptions.Item>
          {order?.cancellation_reason && (
            <Descriptions.Item label="取消原因" span={2}>
              <Text type="danger">{order.cancellation_reason}</Text>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      {/* Products */}
      <Card title="商品明细" style={{ marginBottom: 16 }}>
        <Table
          columns={productColumns}
          dataSource={products}
          rowKey={(r) => r.offer_id || r.name || Math.random().toString()}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无商品明细数据' }}
        />
      </Card>

      {/* AI 异常检测 */}
      <Card
        title={
          <Space>
            <WarningOutlined style={{ color: '#faad14' }} />
            <span>AI 异常检测</span>
          </Space>
        }
        size="small"
        style={{ marginBottom: 16 }}
        extra={
          <Button
            type="link" size="small" icon={<RobotOutlined />}
            onClick={handleAnalyzeAnomaly}
            loading={anomalyLoading}
          >
            AI 分析
          </Button>
        }
      >
        {anomalyError && (
          <Alert type="error" message={anomalyError} showIcon style={{ marginBottom: 12 }} closable onClose={() => setAnomalyError(null)} />
        )}

        {anomalyLoading && (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <Spin tip="AI 分析中…" />
          </div>
        )}

        {anomalyResult && !anomalyLoading && (
          <div>
            <Row gutter={16} style={{ marginBottom: 12 }}>
              <Col span={8}>
                <Statistic
                  title="风险评分"
                  value={anomalyResult.risk_score}
                  suffix="/100"
                  valueStyle={{ color: anomalyResult.risk_level === 'high' ? '#ff4d4f' : anomalyResult.risk_level === 'medium' ? '#faad14' : '#52c41a' }}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="风险等级"
                  valueRender={() => (
                    <Tag color={anomalyResult.risk_level === 'high' ? 'red' : anomalyResult.risk_level === 'medium' ? 'orange' : 'green'} style={{ fontSize: 16, padding: '2px 12px' }}>
                      {anomalyResult.risk_level === 'high' ? '高风险' : anomalyResult.risk_level === 'medium' ? '中风险' : '低风险'}
                    </Tag>
                  )}
                />
              </Col>
              <Col span={8}>
                <Statistic
                  title="异常项"
                  value={anomalyResult.anomalies?.length || 0}
                />
              </Col>
            </Row>

            {anomalyResult.anomalies?.length > 0 && (
              <div>
                <Text strong style={{ fontSize: 13 }}>异常明细</Text>
                <Table
                  dataSource={anomalyResult.anomalies}
                  columns={[
                    { title: '类型', dataIndex: 'type', key: 'type', width: 120,
                      render: (v: string) => <Tag color="volcano">{v}</Tag>,
                    },
                    { title: '说明', dataIndex: 'detail', key: 'detail' },
                    { title: '严重程度', dataIndex: 'severity', key: 'severity', width: 100,
                      render: (v: string) => (
                        <Tag color={v === 'high' ? 'red' : v === 'medium' ? 'orange' : 'blue'}>
                          {v === 'high' ? '严重' : v === 'medium' ? '中等' : '轻微'}
                        </Tag>
                      ),
                    },
                  ]}
                  rowKey="type"
                  pagination={false}
                  size="small"
                  style={{ marginTop: 8 }}
                />
              </div>
            )}

            {anomalyResult.summary && (
              <Alert
                type={anomalyResult.risk_level === 'high' ? 'error' : anomalyResult.risk_level === 'medium' ? 'warning' : 'success'}
                message={anomalyResult.summary}
                style={{ marginTop: 12 }}
                showIcon
              />
            )}
          </div>
        )}

        {!anomalyResult && !anomalyLoading && !anomalyError && (
          <div style={{ textAlign: 'center', padding: 16, color: '#bbb' }}>
            <WarningOutlined style={{ fontSize: 22, marginBottom: 6 }} />
            <div style={{ fontSize: 13 }}>AI 将分析大额订单、数量异常、地址风险等</div>
          </div>
        )}
      </Card>

      {/* AI Purchase Price Calculator */}
      <Card
        title={
          <Space>
            <RobotOutlined style={{ color: '#1677FF' }} />
            <span>AI 建议采购价</span>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <div style={{ marginBottom: 16, background: '#f6f8fa', padding: 16, borderRadius: 8 }}>
          <Row gutter={24} align="middle">
            <Col>
              <Text strong>目标利润率:</Text>
            </Col>
            <Col>
              <InputNumber
                min={0}
                max={100}
                value={targetMargin}
                onChange={(v) => setTargetMargin(v ?? 20)}
                formatter={(v) => `${v}%`}
                parser={(v) => parseFloat(v?.replace('%', '') || '20')}
                style={{ width: 100 }}
              />
            </Col>
            <Col>
              <Text type="secondary" style={{ fontSize: 12 }}>
                针对一件代发场景，计算最高采购成本
              </Text>
            </Col>
            <Col flex="auto" style={{ textAlign: 'right' }}>
              <Button
                type="primary"
                icon={<DollarOutlined />}
                onClick={handleCalcPurchasePrice}
                loading={calcLoading}
              >
                AI 计算最高采购价
              </Button>
            </Col>
          </Row>
        </div>

        {calcError && (
          <Alert type="error" message={calcError} showIcon style={{ marginBottom: 16 }} closable onClose={() => setCalcError(null)} />
        )}

        {calcLoading && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin tip="AI 计算中…" />
          </div>
        )}

        {calcResult && !calcLoading && (
          <div>
            <Row gutter={24} style={{ marginBottom: 20 }}>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center', background: calcResult.profitable ? '#f6ffed' : '#fff2f0' }}>
                  <Statistic
                    title="最高采购价 (CNY)"
                    value={calcResult.max_purchase_price_cny}
                    precision={2}
                    prefix="¥"
                    valueStyle={{ color: calcResult.profitable ? '#52c41a' : '#ff4d4f', fontSize: 28 }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Statistic
                    title="售价 (CNY)"
                    value={calcResult.selling_price_cny}
                    precision={2}
                    prefix="¥"
                    valueStyle={{ fontSize: 22 }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Statistic
                    title="预期利润 (CNY)"
                    value={calcResult.profit_cny}
                    precision={2}
                    prefix="¥"
                    valueStyle={{ color: '#1677FF', fontSize: 22 }}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Statistic
                    title="利润率"
                    value={calcResult.profit_margin_pct}
                    suffix="%"
                    precision={1}
                    valueStyle={{ fontSize: 22 }}
                  />
                </Card>
              </Col>
            </Row>

            <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="商品重量">
                {calcResult.source.weight_kg ? `${calcResult.source.weight_kg} kg` : '未知'}
                <Tag style={{ marginLeft: 8 }} color="blue">
                  {CATEGORY_WEIGHT_LABELS[calcResult.source.weight_from] || calcResult.source.weight_from}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="商品类目">
                {calcResult.source.category_name || '未分类'}
                {calcResult.source.category_from && (
                  <Tag style={{ marginLeft: 8 }} color="blue">{calcResult.source.category_from}</Tag>
                )}
              </Descriptions.Item>
            </Descriptions>

            <Divider style={{ margin: '12px 0' }} />
            <Text strong style={{ fontSize: 13 }}>费用明细</Text>
            <Table
              columns={costColumns}
              dataSource={costData}
              pagination={false}
              size="small"
              style={{ marginTop: 8 }}
              summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0}><Text strong>合计费用</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={1}>
                    <Text strong>
                      ¥{costData.reduce((s, r) => s + r.amount, 0).toFixed(2)}
                    </Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={2} />
                </Table.Summary.Row>
              )}
            />
          </div>
        )}

        {!calcResult && !calcLoading && !calcError && (
          <div style={{ textAlign: 'center', padding: 20, color: '#bbb' }}>
            <InfoCircleOutlined style={{ fontSize: 24, marginBottom: 8 }} />
            <div>点击上方按钮，AI 将根据订单商品信息计算最高采购价</div>
          </div>
        )}
      </Card>

      {/* AI Classify Issue (for cancelled orders) */}
      {order?.cancellation_reason && (
        <Card
          title={
            <Space>
              <FileTextOutlined style={{ color: '#faad14' }} />
              <span>AI 取消原因分类</span>
            </Space>
          }
          style={{ marginBottom: 16 }}
        >
          <ClassifyIssueSection
            postingNumber={id!}
            shopId={currentShop}
            orderType={orderType}
            cancelReason={order.cancellation_reason}
          />
        </Card>
      )}
    </div>
  )
}

/* ── Classify Issue Sub-component ── */
function ClassifyIssueSection({
  postingNumber, shopId, orderType, cancelReason,
}: {
  postingNumber: string
  shopId: string
  orderType: string
  cancelReason: string
}) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)

  async function handleClassify() {
    setLoading(true)
    try {
      const { data } = await axios.post(
        `/api/orders/${postingNumber}/ai/classify-issue`,
        null,
        { params: { shop_id: shopId, order_type: orderType, cancel_reason: cancelReason } },
      )
      setResult(data)
    } catch (e: any) {
      message.error('分类失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <Text type="secondary">取消原因: </Text>
        <Text>{cancelReason}</Text>
      </div>
      <Button icon={<RobotOutlined />} onClick={handleClassify} loading={loading}>
        AI 分类
      </Button>
      {result && !loading && (
        <div style={{ marginTop: 16, padding: 16, background: '#f6f8fa', borderRadius: 8 }}>
          <Descriptions column={1} size="small">
            <Descriptions.Item label="主分类">
              <Tag color="blue">{result.category}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="子分类">{result.sub_category || '—'}</Descriptions.Item>
            <Descriptions.Item label="是否可操作">
              {result.actionable ? <Tag color="green">是</Tag> : <Tag color="red">否</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="处理建议">{result.suggestion || '—'}</Descriptions.Item>
          </Descriptions>
        </div>
      )}
    </div>
  )
}
