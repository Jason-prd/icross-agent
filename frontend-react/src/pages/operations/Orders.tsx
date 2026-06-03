import { useState } from 'react'
import { Card, Segmented, Space, Button, Modal, Descriptions, message, Popconfirm, Tabs, Tag, Typography, Spin, Alert, Table, Tooltip, Row, Col, InputNumber, Image } from 'antd'
import { SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, RollbackOutlined, SendOutlined, RobotOutlined, FileSearchOutlined, WarningOutlined, DownloadOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import StatusTag from '../../components/StatusTag'
import SyncIndicator from '../../components/SyncIndicator'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { formatPrice } from '../../utils/currency'
import axios from 'axios'

const { Text } = Typography

interface Order {
  id: string
  posting_number: string
  status: string
  price: number
  products_count: number
  order_type: string
  created_at: string
  products?: OrderProduct[]
}

interface OrderProduct {
  name: string
  offer_id: string
  quantity: number
  price: number
  images?: string[]
  sku?: string
}

interface SkuPurchasePriceResult {
  offer_id: string
  product_name: string
  quantity: number
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
  logistics_detail?: {
    cost_cny: number
    warehouse: string
    base_fee: number
    price_per_g: number
    tier_label: string
  }
  source: {
    weight_kg: number | null
    category_name: string
    weight_from: string
    category_from: string
  }
}

interface ReturnItem {
  id: string
  return_id: string
  posting_number: string
  product_name: string
  status: string
  reason: string
  created_at: string
  price: number
}

/* ── FBO Orders Tab ── */
function FboTab({ currentShop, onDetail }: { currentShop: string; onDetail: (pn: string) => void }) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['fbo-orders', currentShop, page, pageSize, statusFilter],
    queryFn: async () => {
      const { data } = await axios.get('/api/fbo/orders', {
        params: { shop_id: currentShop, limit: pageSize, offset: (page - 1) * pageSize, status: statusFilter },
      })
      return data
    },
  })

  const orders: Order[] = data?.items || []
  const total = data?.total || 0

  const columns = [
    { key: 'posting_number', title: '订单号', dataIndex: 'posting_number', width: 180 },
    {
      key: 'status', title: '状态', dataIndex: 'status', width: 120,
      render: (v: string) => <StatusTag status={v} />,
    },
    {
      key: 'status_group', title: '分类', dataIndex: 'status_group', width: 80,
      render: (v: string) => {
        const labels: Record<string, { label: string; color: string }> = {
          pending: { label: '待配送', color: 'orange' },
          delivering: { label: '配送中', color: 'blue' },
          completed: { label: '已完成', color: 'green' },
          cancelled: { label: '已取消', color: 'red' },
        }
        const info = labels[v] || { label: v, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      key: 'price', title: '金额', width: 120,
      render: (_: any, r: Order) => {
        const total = r.products?.reduce((s: number, p: OrderProduct) => s + (Number(p.price) || 0) * (p.quantity || 1), 0)
        return total ? formatPrice(total, 'RUB') : '—'
      },
    },
    {
      key: 'products_count', title: '商品数', width: 80,
      render: (_: any, r: Order) => r.products?.length || '—',
    },
    {
      key: 'created_at', title: '时间', width: 170,
      render: (_: any, r: Order) => {
        const t = r.created_at || (r as any).in_process_at || (r as any).shipment_date
        return t ? new Date(t).toLocaleString('zh-CN') : '—'
      },
    },
    {
      key: 'actions', title: '操作', width: 80, fixed: 'right' as const,
      render: (_: any, r: Order) => (
        <Button size="small" type="link" onClick={() => onDetail(r.posting_number)}>详情</Button>
      ),
    },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Segmented
          value={statusFilter || 'all'}
          onChange={(v) => { setStatusFilter(v === 'all' ? undefined : String(v)); setPage(1) }}
          options={[
            { label: '全部', value: 'all' },
            { label: '待配送', value: 'awaiting_deliver' },
            { label: '配送中', value: 'delivering' },
            { label: '已完成', value: 'delivered' },
            { label: '已取消', value: 'cancelled' },
          ]}
        />
      </Card>

      <DataTable
        columns={columns}
        data={orders}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={pageSize}
        onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
        onRefresh={refetch}
        emptyText="暂无 FBO 订单"
      />
    </div>
  )
}

/* ── Returns Tab ── */
function ReturnsTab({ currentShop }: { currentShop: string }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [tab, setTab] = useState('fbo')
  const [detailId, setDetailId] = useState<string | null>(null)

  // AI decision modal
  const [aiDecisionModal, setAiDecisionModal] = useState<{ open: boolean; loading: boolean; returnId: string; result: any }>({
    open: false, loading: false, returnId: '', result: null,
  })
  // AI pattern analysis modal
  const [aiPatternModal, setAiPatternModal] = useState<{ open: boolean; loading: boolean; result: any }>({
    open: false, loading: false, result: null,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['returns', currentShop, page, tab],
    queryFn: async () => {
      const endpoint = tab === 'fbs' ? '/api/ozon/fbs-returns' : '/api/ozon/returns'
      const { data } = await axios.get(endpoint, {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const { data: detailData, isLoading: detailLoading } = useQuery({
    queryKey: ['return-detail', detailId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/ozon/returns/${detailId}`)
      return data
    },
    enabled: !!detailId,
  })

  const acceptMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.post('/api/ozon/returns/accept', { return_id: id, shop_id: currentShop })
    },
    onSuccess: () => { message.success('已验收'); queryClient.invalidateQueries({ queryKey: ['returns'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const rejectMutation = useMutation({
    mutationFn: async ({ id, comment }: { id: string; comment: string }) => {
      await axios.post('/api/ozon/returns/reject', { return_id: id, comment, shop_id: currentShop })
    },
    onSuccess: () => { message.success('已拒绝'); queryClient.invalidateQueries({ queryKey: ['returns'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const refundMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.post('/api/ozon/returns/refund', { return_id: id, shop_id: currentShop })
    },
    onSuccess: () => { message.success('已退款'); queryClient.invalidateQueries({ queryKey: ['returns'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const items: ReturnItem[] = data?.returns || data?.items || []
  const total = data?.total || data?.total_count || 0

  const columns = [
    { key: 'return_id', title: '退货 ID', dataIndex: 'return_id', width: 140 },
    { key: 'posting_number', title: '订单号', dataIndex: 'posting_number', width: 160 },
    { key: 'product_name', title: '商品', dataIndex: 'product_name', width: 200 },
    { key: 'status', title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
    { key: 'reason', title: '原因', dataIndex: 'reason', width: 160 },
    { key: 'price', title: '金额', dataIndex: 'price', width: 100, render: (v: number) => formatPrice(v, 'RUB') },
    { key: 'created_at', title: '时间', dataIndex: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    {
      key: 'actions', title: '操作', width: 280, fixed: 'right' as const,
      render: (_: any, record: ReturnItem) => (
        <Space size="small" wrap>
          <Button size="small" onClick={() => setDetailId(record.return_id)}>详情</Button>
          <Popconfirm title="确认验收此退货？" onConfirm={() => acceptMutation.mutate(record.return_id)}>
            <Button size="small" type="primary" icon={<CheckCircleOutlined />}>验收</Button>
          </Popconfirm>
          <Popconfirm title="确认拒绝此退货？" onConfirm={() => rejectMutation.mutate({ id: record.return_id, comment: 'seller rejected' })}>
            <Button size="small" danger icon={<CloseCircleOutlined />}>拒绝</Button>
          </Popconfirm>
          <Button size="small" icon={<RollbackOutlined />} onClick={() => refundMutation.mutate(record.return_id)}>退款</Button>
          <Button
            size="small"
            icon={<RobotOutlined />}
            onClick={async () => {
              setAiDecisionModal({ open: true, loading: true, returnId: record.return_id, result: null })
              try {
                const { data } = await axios.post(`/api/returns/${record.return_id}/ai/decision`, null, {
                  params: { shop_id: currentShop },
                })
                setAiDecisionModal(prev => ({ ...prev, loading: false, result: data }))
              } catch (e: any) {
                message.error('AI 决策分析失败')
                setAiDecisionModal(prev => ({ ...prev, loading: false }))
              }
            }}
          >
            AI 决策
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Space>
          <Button
            size="small"
            icon={<FileSearchOutlined />}
            onClick={async () => {
              setAiPatternModal({ open: true, loading: true, result: null })
              try {
                const { data } = await axios.post('/api/returns/ai/pattern-analysis', null, {
                  params: { shop_id: currentShop, days: 30 },
                })
                setAiPatternModal(prev => ({ ...prev, loading: false, result: data }))
              } catch {
                message.error('AI 模式分析失败')
                setAiPatternModal(prev => ({ ...prev, loading: false }))
              }
            }}
          >
            AI 模式分析
          </Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Segmented
          value={tab}
          onChange={(v) => { setTab(String(v)); setPage(1) }}
          options={[
            { label: 'FBO 退货', value: 'fbo' },
            { label: 'FBS 退货', value: 'fbs' },
          ]}
        />
      </Card>

      <DataTable
        columns={columns}
        data={items}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={20}
        onChange={(p) => setPage(p)}
        emptyText="暂无退货记录"
      />

      {/* Detail Modal */}
      <Modal
        title="退货详情"
        open={!!detailId}
        onCancel={() => setDetailId(null)}
        footer={null}
        width={600}
      >
        {detailLoading ? <p>加载中…</p> : detailData ? (
          <Descriptions column={2} size="small" bordered>
            {Object.entries(detailData).map(([key, val]) => (
              <Descriptions.Item key={key} label={key} span={2}>
                {String(val ?? '—')}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : <p>无数据</p>}
      </Modal>

      {/* AI Decision Modal */}
      <Modal
        title={<span><RobotOutlined style={{ marginRight: 8 }} />AI 退货决策建议</span>}
        open={aiDecisionModal.open}
        onCancel={() => setAiDecisionModal({ open: false, loading: false, returnId: '', result: null })}
        footer={[
          <Button key="close" onClick={() => setAiDecisionModal({ open: false, loading: false, returnId: '', result: null })}>
            关闭
          </Button>,
        ]}
        width={560}
      >
        {aiDecisionModal.loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="AI 分析中…" /></div>
        ) : aiDecisionModal.result ? (
          <div>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="退货 ID">{aiDecisionModal.result.return_id}</Descriptions.Item>
              <Descriptions.Item label="原始原因">{aiDecisionModal.result.original_reason}</Descriptions.Item>
              <Descriptions.Item label="建议操作">
                <Tag color={aiDecisionModal.result.recommendation === 'accept' ? 'green' : aiDecisionModal.result.recommendation === 'reject' ? 'red' : 'orange'}>
                  {aiDecisionModal.result.recommendation === 'accept' ? '同意退款' : aiDecisionModal.result.recommendation === 'reject' ? '拒绝退款' : '部分退款'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="置信度">
                <Tag>{aiDecisionModal.result.confidence}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="建议退款金额">
                {aiDecisionModal.result.suggested_refund_amount ? `${aiDecisionModal.result.suggested_refund_amount} RUB` : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="分析理由">{aiDecisionModal.result.reasoning}</Descriptions.Item>
              <Descriptions.Item label="风险提示">
                {aiDecisionModal.result.risks?.length > 0
                  ? aiDecisionModal.result.risks.map((r: string, i: number) => <div key={i}>· {r}</div>)
                  : '无'}
              </Descriptions.Item>
            </Descriptions>
          </div>
        ) : <p>加载失败</p>}
      </Modal>

      {/* AI Pattern Analysis Modal */}
      <Modal
        title={<span><FileSearchOutlined style={{ marginRight: 8 }} />AI 退货模式分析</span>}
        open={aiPatternModal.open}
        onCancel={() => setAiPatternModal({ open: false, loading: false, result: null })}
        footer={[
          <Button key="close" onClick={() => setAiPatternModal({ open: false, loading: false, result: null })}>
            关闭
          </Button>,
        ]}
        width={640}
      >
        {aiPatternModal.loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="AI 分析中…" /></div>
        ) : aiPatternModal.result ? (
          aiPatternModal.result.has_data === false ? (
            <Alert type="info" message={aiPatternModal.result.message || '暂无退货数据'} showIcon />
          ) : (
            <div>
              <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
                <Descriptions.Item label="总退货数">{aiPatternModal.result.total_returns}</Descriptions.Item>
                <Descriptions.Item label="总金额">{aiPatternModal.result.total_amount} RUB</Descriptions.Item>
              </Descriptions>
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="分析摘要">{aiPatternModal.result.summary}</Descriptions.Item>
                <Descriptions.Item label="关键发现">
                  {aiPatternModal.result.key_findings?.map((f: string, i: number) => <div key={i}>· {f}</div>)}
                </Descriptions.Item>
                <Descriptions.Item label="主要原因">
                  {aiPatternModal.result.top_reasons?.map((r: string, i: number) => <Tag key={i} style={{ marginBottom: 4 }}>{r}</Tag>)}
                </Descriptions.Item>
                <Descriptions.Item label="改进建议">
                  {aiPatternModal.result.suggestions?.map((s: string, i: number) => <div key={i}>· {s}</div>)}
                </Descriptions.Item>
                <Descriptions.Item label="风险等级">
                  <Tag color={aiPatternModal.result.risk_level === 'high' ? 'red' : aiPatternModal.result.risk_level === 'low' ? 'green' : 'orange'}>
                    {aiPatternModal.result.risk_level === 'high' ? '高风险' : aiPatternModal.result.risk_level === 'low' ? '低风险' : '中风险'}
                  </Tag>
                </Descriptions.Item>
              </Descriptions>
            </div>
          )
        ) : <p>加载失败</p>}
      </Modal>
    </div>
  )
}

/* ── FBS Orders Tab ── */
function FbsTab({ currentShop, onDetail }: { currentShop: string; onDetail: (pn: string) => void }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['fbs-orders', currentShop, page, pageSize, statusFilter],
    queryFn: async () => {
      const { data } = await axios.get('/api/fbs/orders', {
        params: {
          shop_id: currentShop,
          limit: pageSize,
          offset: (page - 1) * pageSize,
          status: statusFilter,
        },
      })
      return data
    },
  })

  const prepareMutation = useMutation({
    mutationFn: async (postingIds: string[]) => {
      await axios.post('/api/fbs/ship', { shop_id: currentShop, posting_ids: postingIds })
    },
    onSuccess: () => { message.success('已备货完成'); queryClient.invalidateQueries({ queryKey: ['fbs-orders'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const downloadLabel = async (postingNumber: string) => {
    try {
      const response = await axios.post('/api/fbs/package-label', {
        shop_id: currentShop,
        posting_numbers: [postingNumber],
      }, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
      window.open(url)
    } catch (e: any) {
      message.error('下载运单失败: ' + (e?.response?.data?.detail || e.message))
    }
  }

  const orders: Order[] = data?.items || []
  const total = data?.total || 0

  const renderActions = (record: Order) => {
    const statusGroup = (record as any).status_group || ''
    const buttons: React.ReactNode[] = [
      <Button key="detail" size="small" type="link" onClick={() => onDetail(record.posting_number)}>详情</Button>,
    ]
    if (statusGroup === 'pending') {
      buttons.push(
        <Button
          key="prepare"
          size="small"
          type="primary"
          icon={<SendOutlined />}
          loading={prepareMutation.isPending}
          onClick={() => prepareMutation.mutate([record.posting_number])}
        >
          备货
        </Button>,
      )
    } else if (statusGroup === 'ready_to_ship') {
      buttons.push(
        <Button
          key="label"
          size="small"
          icon={<DownloadOutlined />}
          onClick={() => downloadLabel(record.posting_number)}
        >
          下载运单
        </Button>,
      )
    }
    return <Space size="small">{buttons}</Space>
  }

  const columns = [
    { key: 'posting_number', title: '订单号', dataIndex: 'posting_number', width: 180 },
    {
      key: 'status', title: '状态', dataIndex: 'status', width: 120,
      render: (v: string) => <StatusTag status={v} />,
    },
    {
      key: 'status_group', title: '分类', dataIndex: 'status_group', width: 80,
      render: (v: string) => {
        const labels: Record<string, { label: string; color: string }> = {
          pending: { label: '待处理', color: 'orange' },
          ready_to_ship: { label: '待配送', color: 'blue' },
          delivering: { label: '配送中', color: 'purple' },
          completed: { label: '已完成', color: 'green' },
          cancelled: { label: '已取消', color: 'red' },
        }
        const info = labels[v] || { label: v, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      key: 'price', title: '金额', width: 120,
      render: (_: any, r: Order) => {
        const total = r.products?.reduce((s: number, p: OrderProduct) => s + (Number(p.price) || 0) * (p.quantity || 1), 0)
        return total ? formatPrice(total, 'RUB') : '—'
      },
    },
    {
      key: 'products_count', title: '商品数', width: 80,
      render: (_: any, r: Order) => r.products?.length || '—',
    },
    {
      key: 'created_at', title: '时间', width: 170,
      render: (_: any, r: Order) => {
        const t = r.created_at || (r as any).in_process_at || (r as any).shipment_date
        return t ? new Date(t).toLocaleString('zh-CN') : '—'
      },
    },
    {
      key: 'actions', title: '操作', width: 200, fixed: 'right' as const,
      render: (_: any, record: Order) => renderActions(record),
    },
  ]

  return (
    <div>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Segmented
          value={statusFilter || 'all'}
          onChange={(v) => { setStatusFilter(v === 'all' ? undefined : String(v)); setPage(1) }}
          options={[
            { label: '全部', value: 'all' },
            { label: '待处理', value: 'awaiting_packaging' },
            { label: '待配送', value: 'awaiting_deliver' },
            { label: '配送中', value: 'delivering' },
            { label: '已完成', value: 'delivered' },
            { label: '已取消', value: 'cancelled' },
          ]}
        />
      </Card>

      <DataTable
        columns={columns}
        data={orders}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={pageSize}
        onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
        onRefresh={refetch}
        rowKey="posting_number"
        emptyText="暂无 FBS 订单"
      />
    </div>
  )
}

/* ── Main Combined Page ── */
export default function Orders() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const [activeTab, setActiveTab] = useState('fbo')

  // Sync state (tab-level, shared across FBO/FBS tabs)
  const queryClient = useQueryClient()
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)

  const syncMutation = useMutation({
    mutationFn: async () => {
      const { data } = await axios.post('/api/orders/sync', null, {
        params: { shop_id: currentShop },
      })
      return data
    },
    onSuccess: () => {
      setLastSyncTime(new Date().toISOString())
      setSyncError(null)
      message.success('订单同步成功')
      queryClient.invalidateQueries({ queryKey: ['fbo-orders'] })
      queryClient.invalidateQueries({ queryKey: ['fbs-orders'] })
    },
    onError: (e: any) => {
      setSyncError(e.message || '同步失败')
      message.error('订单同步失败')
    },
  })

  // Shared detail modal state
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [detailPosting, setDetailPosting] = useState<string | null>(null)
  const [detailOrder, setDetailOrder] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [skuPrices, setSkuPrices] = useState<Record<string, SkuPurchasePriceResult>>({})
  const [skuPricesLoading, setSkuPricesLoading] = useState(false)
  const [targetMargin, setTargetMargin] = useState(20)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisResult, setAnalysisResult] = useState<any>(null)
  const [classifying, setClassifying] = useState(false)
  const [classifyResult, setClassifyResult] = useState<any>(null)

  const fetchPrices = async (postingNumber: string, margin: number) => {
    try {
      setSkuPricesLoading(true)
      const priceRes = await axios.post(`/api/orders/${postingNumber}/ai/max-purchase-price`, null, {
        params: { shop_id: currentShop, target_margin: margin }
      })
      const products = priceRes.data.products || []
      const priceMap: Record<string, SkuPurchasePriceResult> = {}
      products.forEach((p: SkuPurchasePriceResult) => { priceMap[p.offer_id] = p })
      setSkuPrices(priceMap)
    } catch { /* non-critical */ }
    setSkuPricesLoading(false)
  }

  const openDetail = async (postingNumber: string) => {
    setDetailPosting(postingNumber)
    setDetailModalOpen(true)
    setDetailLoading(true)
    setDetailOrder(null)
    setSkuPrices({})
    setAnalysisResult(null)
    setClassifyResult(null)

    try {
      const detailRes = await axios.get('/api/order-detail', {
        params: { shop_id: currentShop, posting_number: postingNumber }
      })
      setDetailOrder(detailRes.data.order)
    } catch (e: any) {
      message.error('获取订单详情失败')
    }
    setDetailLoading(false)

    // Fetch per-SKU purchase prices with default margin
    setTargetMargin(20)
    await fetchPrices(postingNumber, 20)
  }

  const runAnalysis = async () => {
    if (!detailPosting) return
    setAnalyzing(true)
    setAnalysisResult(null)
    try {
      const { data } = await axios.post(`/api/orders/${detailPosting}/ai/analyze`, null, {
        params: { shop_id: currentShop }
      })
      setAnalysisResult(data)
    } catch {
      message.error('AI 分析失败')
    }
    setAnalyzing(false)
  }

  const runClassify = async () => {
    if (!detailPosting || !detailOrder?.cancellation_reason) return
    setClassifying(true)
    setClassifyResult(null)
    try {
      const { data } = await axios.post(`/api/orders/${detailPosting}/ai/classify-issue`, null, {
        params: { shop_id: currentShop, cancel_reason: detailOrder.cancellation_reason }
      })
      setClassifyResult(data)
    } catch {
      message.error('AI 分类失败')
    }
    setClassifying(false)
  }

  const closeDetail = () => {
    setDetailModalOpen(false)
    setDetailPosting(null)
  }

  const tabItems = [
    { key: 'fbo', label: 'FBO 订单', children: <FboTab currentShop={currentShop} onDetail={openDetail} /> },
    { key: 'fbs', label: 'FBS 订单', children: <FbsTab currentShop={currentShop} onDetail={openDetail} /> },
    { key: 'returns', label: '退货管理', children: <ReturnsTab currentShop={currentShop} /> },
  ]

  // Determine whether current order is completed (show financial data)
  const isCompleted = detailOrder?.status_group === 'completed' || detailOrder?.status === 'delivered'
  const isCancelled = detailOrder?.status_group === 'cancelled' || detailOrder?.status === 'cancelled'
  const isDelivering = detailOrder?.status_group === 'delivering' || detailOrder?.status === 'delivering'
  const isPending = detailOrder?.status_group === 'pending' || detailOrder?.status === 'awaiting_packaging'
  const isReadyToShip = detailOrder?.status_group === 'ready_to_ship'

  return (
    <div>
      <PageHeader title="订单中心" subtitle="FBO 订单 / FBS 订单 / 退货管理" />

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <Space>
          <SyncIndicator
            lastSyncAt={lastSyncTime}
            syncing={syncMutation.isPending}
            error={syncError}
            onSync={() => syncMutation.mutate()}
          />
          <Button icon={<SyncOutlined />} onClick={() => syncMutation.mutate()} loading={syncMutation.isPending} size="small">
            同步 Ozon
          </Button>
        </Space>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        style={{ marginTop: -8 }}
      />

      {/* Detail Modal */}
      <Modal
        title={`订单详情 — ${detailPosting || ''}`}
        open={detailModalOpen}
        onCancel={closeDetail}
        footer={null}
        width={900}
      >
        {detailLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="加载中…" /></div>
        ) : detailOrder ? (
          <div>
            {/* ── Basic Info ── */}
            <Card size="small" style={{ marginBottom: 16 }}>
              <Descriptions column={3} size="small">
                <Descriptions.Item label="订单号" span={3}>{detailOrder.posting_number || detailOrder.id}</Descriptions.Item>
                <Descriptions.Item label="状态">
                  <StatusTag status={detailOrder.status} />
                </Descriptions.Item>
                <Descriptions.Item label="类型">{detailOrder.order_type || (detailOrder.is_fbo ? 'FBO' : 'FBS')}</Descriptions.Item>
                <Descriptions.Item label="创建时间">
                  {detailOrder.created_at ? new Date(detailOrder.created_at).toLocaleString('zh-CN') : '—'}
                </Descriptions.Item>
                <Descriptions.Item label="配送方式">
                  {detailOrder.analytics_data?.delivery_type || detailOrder.analytics?.delivery_type || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="仓库">
                  {detailOrder.analytics_data?.warehouse || detailOrder.analytics?.warehouse || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="物流商">
                  {detailOrder.analytics_data?.tpl_provider || detailOrder.analytics?.tpl_provider || '—'}
                </Descriptions.Item>
                {detailOrder.tracking_number && (
                  <Descriptions.Item label="快递单号">{detailOrder.tracking_number}</Descriptions.Item>
                )}
                {detailOrder.shipment_date && (
                  <Descriptions.Item label="最晚发货">
                    {new Date(detailOrder.shipment_date).toLocaleString('zh-CN')}
                  </Descriptions.Item>
                )}
                {detailOrder.delivering_date && (
                  <Descriptions.Item label="配送时间">
                    {new Date(detailOrder.delivering_date).toLocaleString('zh-CN')}
                  </Descriptions.Item>
                )}
                {isCancelled && detailOrder.cancellation_reason && (
                  <Descriptions.Item label="取消原因" span={3}>
                    <Text type="danger">{detailOrder.cancellation_reason}</Text>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>

            {/* ── Pending/Ready: Purchase Price Calculator (Table with expandable rows) ── */}
            {(isPending || isReadyToShip) && (
              <Card
                size="small"
                title="采购价计算"
                style={{ marginBottom: 16 }}
                extra={
                  <Space>
                    <Text type="secondary">目标利润率:</Text>
                    <InputNumber
                      size="small"
                      min={0}
                      max={100}
                      value={targetMargin}
                      onChange={(v) => setTargetMargin(v ?? 20)}
                      formatter={(v) => `${v}%`}
                      parser={(v) => Number(v?.replace('%', '') ?? 20)}
                      style={{ width: 80 }}
                    />
                    <Button
                      size="small"
                      type="primary"
                      onClick={() => detailPosting && fetchPrices(detailPosting, targetMargin)}
                      loading={skuPricesLoading}
                    >
                      重新计算
                    </Button>
                  </Space>
                }
              >
                {skuPricesLoading ? (
                  <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
                ) : Object.keys(skuPrices).length === 0 ? (
                  <Text type="secondary">暂无采购价数据</Text>
                ) : (
                  <Table
                    dataSource={detailOrder.products || []}
                    rowKey={(r: any) => r.offer_id || r.sku}
                    size="small"
                    pagination={false}
                    expandable={{
                      expandedRowRender: (record: any) => {
                        const p = skuPrices[record.offer_id]
                        if (!p) return <Text type="secondary">暂无采购价数据</Text>

                        const totalCost =
                          (p.cost_breakdown?.commission_cny || 0) +
                          (p.cost_breakdown?.logistics_cny || 0) +
                          (p.cost_breakdown?.customs_cny || 0) +
                          (p.cost_breakdown?.return_reserve_cny || 0) +
                          (p.cost_breakdown?.packaging_cny || 0)

                        return (
                          <div style={{ padding: '8px 0 8px 48px' }}>
                            <div style={{
                              background: '#fafafa', borderRadius: 6,
                              padding: '8px 12px', maxWidth: 480,
                            }}>
                              <Text strong style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>成本明细</Text>
                              <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                                <tbody>
                                  {[
                                    { label: '佣金', value: p.cost_breakdown?.commission_cny, pct: p.cost_breakdown?.commission_pct },
                                    { label: '物流费', value: p.cost_breakdown?.logistics_cny },
                                    { label: '关税', value: p.cost_breakdown?.customs_cny },
                                    { label: '回款预留 (2%)', value: p.cost_breakdown?.return_reserve_cny },
                                    { label: '包装费', value: p.cost_breakdown?.packaging_cny },
                                  ].map(item => (
                                    <tr key={item.label}>
                                      <td style={{ padding: '2px 8px 2px 0', color: '#666' }}>
                                        {item.label}{item.pct != null ? ` (${item.pct}%)` : ''}
                                      </td>
                                      <td style={{ padding: '2px 0', textAlign: 'right' }}>
                                        {item.value != null ? `¥${item.value.toFixed(2)}` : '—'}
                                      </td>
                                    </tr>
                                  ))}
                                  <tr style={{ borderTop: '1px solid #e8e8e8' }}>
                                    <td style={{ padding: '4px 8px 0 0', fontWeight: 600, color: '#333' }}>
                                      总成本
                                    </td>
                                    <td style={{ padding: '4px 0 0', textAlign: 'right', fontWeight: 600 }}>
                                      ¥{totalCost.toFixed(2)}
                                    </td>
                                  </tr>
                                </tbody>
                              </table>
                            </div>

                            <div style={{ marginTop: 8, display: 'flex', gap: 24, alignItems: 'center', fontSize: 13 }}>
                              <span>
                                建议采购价:{' '}
                                <Text strong style={{ fontSize: 15, color: p.profitable ? '#52c41a' : '#ff4d4f' }}>
                                  ¥{p.max_purchase_price_cny?.toFixed(2)}
                                </Text>
                              </span>
                              <span>
                                利润: <Text type={p.profitable ? undefined : 'danger'}>¥{p.profit_cny?.toFixed(2)}</Text>
                              </span>
                              <Tag color={p.profitable ? 'green' : 'red'}>{p.profit_margin_pct?.toFixed(1)}%</Tag>
                            </div>

                            {p.source && (
                              <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                                重量来源: {p.source.weight_from === 'product' ? '商品资料' : p.source.weight_from === 'estimated' ? '估算' : p.source.weight_from}
                                {p.logistics_detail && ` · 物流: ${p.logistics_detail.warehouse} (${p.logistics_detail.tier_label})`}
                              </div>
                            )}
                          </div>
                        )
                      },
                      rowExpandable: (record: any) => !!skuPrices[record.offer_id],
                    }}
                    columns={[
                      {
                        title: '图片', key: 'image', width: 64,
                        render: (_: any, r: any) => {
                          const imgUrl = r.images?.[0]
                          return imgUrl
                            ? <Image src={imgUrl} width={48} height={48} style={{ objectFit: 'cover', borderRadius: 4 }} preview={{ mask: null }} />
                            : <div style={{
                                width: 48, height: 48, background: '#f5f5f5',
                                borderRadius: 4, display: 'flex', alignItems: 'center',
                                justifyContent: 'center', fontSize: 10, color: '#bbb',
                              }}>无图</div>
                        },
                      },
                      {
                        title: '商品', dataIndex: 'name', key: 'name', width: 200,
                        render: (v: string, r: any) => {
                          const p = skuPrices[r.offer_id]
                          return (
                            <div>
                              <Text strong ellipsis style={{ maxWidth: 180 }}>{v || p?.product_name || '—'}</Text>
                            </div>
                          )
                        },
                      },
                      { title: 'SKU', dataIndex: 'offer_id', key: 'offer_id', width: 100 },
                      { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 60 },
                      {
                        title: '售价 (CNY)', key: 'price', width: 100,
                        render: (_: any, r: any) => {
                          const p = skuPrices[r.offer_id]
                          return p?.selling_price_cny != null ? `¥${p.selling_price_cny.toFixed(2)}` : '—'
                        },
                      },
                      {
                        title: '建议采购价', key: 'purchase_price', width: 110,
                        render: (_: any, r: any) => {
                          const p = skuPrices[r.offer_id]
                          if (!p) return '—'
                          return (
                            <Text strong style={{ color: p.profitable ? '#52c41a' : '#ff4d4f' }}>
                              ¥{p.max_purchase_price_cny?.toFixed(2)}
                            </Text>
                          )
                        },
                      },
                      {
                        title: '利润', key: 'profit', width: 90,
                        render: (_: any, r: any) => {
                          const p = skuPrices[r.offer_id]
                          if (!p) return '—'
                          return <Text type={p.profitable ? undefined : 'danger'}>¥{p.profit_cny?.toFixed(2)}</Text>
                        },
                      },
                      {
                        title: '利润率', key: 'margin', width: 70,
                        render: (_: any, r: any) => {
                          const p = skuPrices[r.offer_id]
                          if (!p) return '—'
                          return <Tag color={p.profitable ? 'green' : 'red'}>{p.profit_margin_pct?.toFixed(1)}%</Tag>
                        },
                      },
                    ]}
                  />
                )}
              </Card>
            )}

            {/* ── Completed: Financial Data ── */}
            {isCompleted && (
              <Card size="small" title="实际费用" style={{ marginBottom: 16 }}>
                {detailOrder.financial_data?.length > 0 ? (
                  <div>
                    <Table
                      dataSource={detailOrder.financial_data}
                      rowKey={(r: any) => r.product_id || r.offer_id}
                      size="small"
                      pagination={false}
                      columns={[
                        { title: '商品 ID', dataIndex: 'product_id', key: 'product_id', width: 80 },
                        { title: '售价', key: 'price', width: 90,
                          render: (_: any, r: any) => formatPrice(Number(r.price) || 0, r.currency_code || 'RUB'),
                        },
                        { title: '原价', key: 'old_price', width: 90,
                          render: (_: any, r: any) => r.old_price ? formatPrice(r.old_price, r.currency_code || 'RUB') : '—',
                        },
                        { title: '佣金', key: 'commission_amount', width: 90,
                          render: (_: any, r: any) => r.commission_amount ? formatPrice(r.commission_amount, r.commissions_currency_code || 'RUB') : '—',
                        },
                        { title: '佣金率', key: 'commission_percent', width: 70,
                          render: (_: any, r: any) => r.commission_percent != null ? `${r.commission_percent}%` : '—',
                        },
                        { title: '打款金额', key: 'payout', width: 100,
                          render: (_: any, r: any) => (
                            <Text strong>{r.payout ? formatPrice(r.payout, r.currency_code || 'RUB') : '—'}</Text>
                          ),
                        },
                        { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 50 },
                      ]}
                    />
                    <div style={{
                      marginTop: 12, padding: '8px 12px', background: '#f6ffed',
                      borderRadius: 6, fontSize: 13,
                    }}>
                      <Space>
                        <Text>订单合计:</Text>
                        <Text strong>
                          打款 {formatPrice(
                            (detailOrder.financial_data || []).reduce((s: number, r: any) => s + (Number(r.payout) || 0), 0),
                            (detailOrder.financial_data[0]?.currency_code || 'RUB'),
                          )}
                        </Text>
                        <Text type="secondary">|</Text>
                        <Text>
                          佣金 {formatPrice(
                            (detailOrder.financial_data || []).reduce((s: number, r: any) => s + (Number(r.commission_amount) || 0), 0),
                            (detailOrder.financial_data[0]?.commissions_currency_code || 'RUB'),
                          )}
                        </Text>
                      </Space>
                    </div>
                  </div>
                ) : (
                  <Text type="secondary">暂无财务数据</Text>
                )}
              </Card>
            )}

            {/* ── Products Table (non-pending, non-ready) ── */}
            {!isPending && !isReadyToShip && (
              <Card size="small" title="商品列表" style={{ marginBottom: 16 }}>
                <Table
                  dataSource={detailOrder.products || []}
                  rowKey={(r: any) => r.offer_id || r.sku}
                  size="small"
                  pagination={false}
                  columns={[
                    { title: '商品', dataIndex: 'name', key: 'name', width: 250 },
                    { title: 'SKU', dataIndex: 'offer_id', key: 'offer_id', width: 100 },
                    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 60 },
                    { title: '售价', key: 'price', width: 100,
                      render: (_: any, r: any) => formatPrice(Number(r.price) || 0, r.currency_code || 'RUB'),
                    },
                  ]}
                />
              </Card>
            )}

            {/* ── AI Actions ── */}
            <Space style={{ marginBottom: 12 }}>
              {isCancelled && detailOrder.cancellation_reason && (
                <Button size="small" icon={<RobotOutlined />} onClick={runClassify} loading={classifying}>
                  AI 取消分类
                </Button>
              )}
              <Button size="small" icon={<RobotOutlined />} onClick={runAnalysis} loading={analyzing}>
                AI 异常分析
              </Button>
            </Space>

            {/* ── AI Results ── */}
            {classifyResult && (
              <Alert style={{ marginBottom: 12 }} type="info" message={
                <div style={{ fontSize: 13 }}>
                  <Text strong>取消分类: {classifyResult.category}</Text>
                  {classifyResult.sub_category && <div>子分类: {classifyResult.sub_category}</div>}
                  {classifyResult.suggestion && <div>建议: {classifyResult.suggestion}</div>}
                </div>
              } />
            )}
            {analysisResult && (
              <Alert
                type={analysisResult.risk_level === 'high' ? 'error' : analysisResult.risk_level === 'medium' ? 'warning' : 'info'}
                message={
                  <div style={{ fontSize: 13 }}>
                    <Text strong>
                      风险等级: {analysisResult.risk_level === 'high' ? '高风险' : analysisResult.risk_level === 'medium' ? '中风险' : '低风险'}
                      &nbsp;({analysisResult.risk_score}/100)
                    </Text>
                    <p style={{ margin: '4px 0 0 0' }}>{analysisResult.summary}</p>
                    {analysisResult.anomalies?.map((a: any, i: number) => (
                      <div key={i}>· {a.type}: {a.detail}</div>
                    ))}
                  </div>
                }
              />
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40 }}><Text type="secondary">无数据</Text></div>
        )}
      </Modal>
    </div>
  )
}
