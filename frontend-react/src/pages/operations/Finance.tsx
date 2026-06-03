import { useState, useMemo } from 'react'
import { Tabs, Card, Row, Col, Statistic, Tag, Space, Button, message, Modal, Typography, Alert, Tooltip } from 'antd'
import { RiseOutlined, FallOutlined, DollarOutlined, RobotOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { formatPrice, getCurrencyInfo } from '../../utils/currency'
import axios from 'axios'

/* ── Transaction Tab ── */
function TransactionTab({ currentShop }: { currentShop: string }) {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['finance-transactions', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/finance/transactions', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const items = data?.transactions || data?.items || []
  const total = data?.total || 0

  return (
    <DataTable
      columns={[
        { key: 'operation_id', title: '操作 ID', dataIndex: 'operation_id', width: 180 },
        { key: 'type', title: '类型', dataIndex: 'type', width: 120 },
        {
          key: 'amount', title: '金额', dataIndex: 'amount', width: 120,
          render: (v: number) => {
            const num = Number(v)
            return (
              <span style={{ color: num >= 0 ? '#22c55e' : '#ef4444', fontWeight: 500 }}>
                {num >= 0 ? '+' : ''}{formatPrice(num, 'RUB')}
              </span>
            )
          },
        },
        { key: 'description', title: '描述', dataIndex: 'description', width: 300 },
        { key: 'date', title: '日期', dataIndex: 'date', width: 170, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
      ]}
      data={items}
      total={total}
      loading={isLoading}
      current={page}
      pageSize={20}
      onChange={(p) => setPage(p)}
      emptyText="暂无交易记录"
    />
  )
}

/* ── Daily Sales Tab ── */
function DailySalesTab({ currentShop }: { currentShop: string }) {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({
    queryKey: ['finance-daily-sales', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/finance/daily-sales', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const items = data?.sales || data?.items || []
  const total = data?.total || 0

  return (
    <DataTable
      columns={[
        { key: 'date', title: '日期', dataIndex: 'date', width: 120 },
        { key: 'revenue', title: '收入', dataIndex: 'revenue', width: 120 },
        { key: 'commission', title: '佣金', dataIndex: 'commission', width: 100 },
        { key: 'logistics', title: '物流', dataIndex: 'logistics', width: 100 },
        { key: 'orders', title: '订单数', dataIndex: 'orders', width: 80 },
      ]}
      data={items}
      total={total}
      loading={isLoading}
      current={page}
      pageSize={20}
      onChange={(p) => setPage(p)}
      emptyText="暂无销售数据"
    />
  )
}

/* ── Profit Tab ── */
function ProfitTab({ currentShop }: { currentShop: string }) {
  const now = new Date()
  const [page, setPage] = useState(1)

  const { data: postingData, isLoading } = useQuery({
    queryKey: ['finance-profit', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/finance/realization-posting', {
        params: { shop_id: currentShop, month: now.getMonth() + 1, year: now.getFullYear() },
      })
      return data
    },
  })

  const { data: productData } = useQuery({
    queryKey: ['products-cost', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/products', {
        params: { shop_id: currentShop, limit: 10000 },
      })
      return data
    },
  })

  // Build cost lookup map: offer_id -> cost_price
  const costMap = useMemo(() => {
    const map = new Map<string, number>()
    const products = productData?.items || productData?.products || []
    for (const p of products) {
      if (p.cost_price) map.set(p.offer_id, Number(p.cost_price))
    }
    return map
  }, [productData])

  // Process posting data with profit calculation
  const rows = useMemo(() => {
    const raw = postingData?.rows || postingData?.items || postingData?.postings || []
    return raw.map((r: any) => {
      const revenue = Number(r.revenue || r.sales || r.amount || 0)
      const commission = Number(r.commission || 0)
      const logistics = Number(r.logistics_cost || r.logistics || 0)
      const costPrice = Number(costMap.get(r.offer_id || r.sku || '') || 0)
      const totalCost = commission + logistics + costPrice
      const profit = revenue - totalCost
      const margin = revenue > 0 ? (profit / revenue) * 100 : 0
      return { ...r, revenue, commission, logistics, costPrice, profit, margin }
    }).sort((a: any, b: any) => b.profit - a.profit)
  }, [postingData, costMap])

  const total = rows.length

  // Summary stats
  const stats = useMemo(() => {
    if (!rows.length) return { revenue: 0, profit: 0, commission: 0, logistics: 0, cost: 0, margin: 0 }
    const revenue = rows.reduce((s: number, r: any) => s + r.revenue, 0)
    const profit = rows.reduce((s: number, r: any) => s + r.profit, 0)
    const commission = rows.reduce((s: number, r: any) => s + r.commission, 0)
    const logistics = rows.reduce((s: number, r: any) => s + r.logistics, 0)
    const cost = rows.reduce((s: number, r: any) => s + r.costPrice, 0)
    return { revenue, profit, commission, logistics, cost, margin: revenue > 0 ? (profit / revenue) * 100 : 0 }
  }, [rows])

  const pageRows = rows.slice((page - 1) * 20, page * 20)

  return (
    <div>
      {/* Summary KPI cards */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col xs={12} sm={6}>
          <Card size="small" styles={{ body: { padding: '14px 16px' } }}>
            <Statistic
              title="总收入"
              value={stats.revenue}
              precision={0}
              prefix={getCurrencyInfo('RUB').symbol}
              valueStyle={{ fontSize: 20, fontWeight: 700, color: '#22c55e' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" styles={{ body: { padding: '14px 16px' } }}>
            <Statistic
              title="净利润"
              value={stats.profit}
              precision={0}
              prefix={<span style={{ color: stats.profit >= 0 ? '#22c55e' : '#ef4444' }}>{getCurrencyInfo('RUB').symbol}</span>}
              valueStyle={{ fontSize: 20, fontWeight: 700, color: stats.profit >= 0 ? '#22c55e' : '#ef4444' }}
              suffix={
                <span style={{ fontSize: 12, marginLeft: 4 }}>
                  <Tag color={stats.margin >= 0 ? 'green' : 'red'}>{stats.margin >= 0 ? '+' : ''}{stats.margin.toFixed(1)}%</Tag>
                </span>
              }
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" styles={{ body: { padding: '14px 16px' } }}>
            <Statistic
              title="佣金"
              value={stats.commission}
              precision={0}
              prefix={getCurrencyInfo('RUB').symbol}
              valueStyle={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" styles={{ body: { padding: '14px 16px' } }}>
            <Statistic
              title="物流成本"
              value={stats.logistics}
              precision={0}
              prefix={getCurrencyInfo('RUB').symbol}
              valueStyle={{ fontSize: 20, fontWeight: 700, color: '#f59e0b' }}
            />
          </Card>
        </Col>
      </Row>

      <DataTable
        columns={[
          { key: 'posting_number', title: '订单号', dataIndex: 'posting_number', width: 160 },
          { key: 'product_name', title: '商品', dataIndex: 'product_name', width: 200 },
          {
            key: 'revenue', title: '收入', dataIndex: 'revenue', width: 100,
            render: (v: number) => formatPrice(v, 'RUB'),
          },
          {
            key: 'commission', title: '佣金', dataIndex: 'commission', width: 80,
            render: (v: number) => <span style={{ color: '#f59e0b' }}>{formatPrice(v, 'RUB')}</span>,
          },
          {
            key: 'logistics', title: '物流', dataIndex: 'logistics', width: 80,
            render: (v: number) => <span style={{ color: '#f59e0b' }}>{formatPrice(v, 'RUB')}</span>,
          },
          {
            key: 'costPrice', title: '成本', dataIndex: 'costPrice', width: 80,
            render: (v: number) => formatPrice(v, 'RUB'),
          },
          {
            key: 'profit', title: '利润', dataIndex: 'profit', width: 100,
            render: (v: number) => (
              <span style={{ color: v >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                {v >= 0 ? '+' : ''}{formatPrice(v, 'RUB')}
              </span>
            ),
          },
          {
            key: 'margin', title: '利润率', dataIndex: 'margin', width: 80,
            render: (v: number) => (
              <Tag color={v >= 20 ? 'green' : v >= 0 ? 'orange' : 'red'}>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</Tag>
            ),
          },
        ]}
        data={pageRows}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={20}
        onChange={(p) => setPage(p)}
        emptyText="暂无本月订单利润数据"
      />
      <Modal title="AI 每日销售评述" open={showAiCommentary} onCancel={() => setShowAiCommentary(false)} footer={null} width={500}>
        {aiCommentary && <div><Alert message={aiCommentary.date} type="info" style={{marginBottom:12}} /><Typography.Text>{aiCommentary.commentary}</Typography.Text>{aiCommentary.highlights?.length>0 && <ul>{aiCommentary.highlights.map((h:string,i:number)=><li key={i}>{h}</li>)}</ul>}{aiCommentary.warnings?.length>0 && <p style={{color:'#ef4444',marginTop:8}}>⚠ {aiCommentary.warnings.join('; ')}</p>}</div>}
      </Modal>
      <Modal title="AI 费用分类" open={showAiTag} onCancel={() => setShowAiTag(false)} footer={null} width={500}>
        {aiTagResult && <div>{Object.entries(aiTagResult.categories||{}).map(([k,v]:[string,any])=><p key={k}><Tag>{k}</Tag> {v.count}笔 / {v.total?.toFixed(0)} RUB</p>)}</div>}
      </Modal>
    </div>)
  )
}

/* ── Main ── */
export default function Finance() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const [aiCommentary, setAiCommentary] = useState<any>(null)
  const [showAiCommentary, setShowAiComment] = useState(false)
  const [aiTagResult, setAiTagResult] = useState<any>(null)
  const [showAiTag, setShowAiTag] = useState(false)

  const aiCommentaryMutation = useMutation({
    mutationFn: async () => { const { data } = await axios.post('/api/finance/ai/daily-commentary', null, { params: { shop_id: currentShop } }); return data },
    onSuccess: (d: any) => { setAiCommentary(d); setShowAiCommentary(true) },
    onError: (e: any) => message.error('AI 分析失败'),
  })
  const aiTagMutation = useMutation({
    mutationFn: async () => { const { data } = await axios.post('/api/finance/ai/tag-transactions', null, { params: { shop_id: currentShop } }); return data },
    onSuccess: (d: any) => { setAiTagResult(d); setShowAiTag(true) },
    onError: (e: any) => message.error('AI 分析失败'),
  })

  return (
    <div>
      <PageHeader title="财务中心" subtitle="交易流水 / 每日销售 / 利润分析" />
      <Tabs
        items={[
          { key: 'transactions', label: '交易流水', children: <TransactionTab currentShop={currentShop} /> },
          { key: 'daily-sales', label: '每日销售', children: <DailySalesTab currentShop={currentShop} /> },
          { key: 'profit', label: '利润分析', children: <ProfitTab currentShop={currentShop} /> },
        ]}
      />
      <Modal title="AI 每日销售评述" open={showAiCommentary} onCancel={() => setShowAiCommentary(false)} footer={null} width={500}>
        {aiCommentary && <div><Alert message={aiCommentary.date} type="info" style={{marginBottom:12}} /><Typography.Text>{aiCommentary.commentary}</Typography.Text>{aiCommentary.highlights?.length>0 && <ul>{aiCommentary.highlights.map((h:string,i:number)=><li key={i}>{h}</li>)}</ul>}{aiCommentary.warnings?.length>0 && <p style={{color:'#ef4444',marginTop:8}}>⚠ {aiCommentary.warnings.join('; ')}</p>}</div>}
      </Modal>
      <Modal title="AI 费用分类" open={showAiTag} onCancel={() => setShowAiTag(false)} footer={null} width={500}>
        {aiTagResult && <div>{Object.entries(aiTagResult.categories||{}).map(([k,v]:[string,any])=><p key={k}><Tag>{k}</Tag> {v.count}笔 / {v.total?.toFixed(0)} RUB</p>)}</div>}
      </Modal>
    </div>)
  )
}
