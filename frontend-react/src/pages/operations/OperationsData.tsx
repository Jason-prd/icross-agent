import { useState } from 'react'
import { Card, Row, Col, Statistic, Table, Tabs, Tag } from 'antd'
import { StockOutlined, RiseOutlined, FallOutlined, TeamOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { formatPrice } from '../../utils/currency'
import axios from 'axios'

export default function OperationsData() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const [aiReplenish, setAiReplenish] = useState<any>(null); const [showAiReplenish, setShowAiReplenish] = useState(false)
  const [aiTrend, setAiTrend] = useState<any>(null); const [showAiTrend, setShowAiTrend] = useState(false)
  const aiReplenishMutation = useMutation({mutationFn: async () => {const {data}=await axios.post('/api/operations-data/ai/replenish',null,{params:{shop_id:currentShop}});return data},onSuccess:(d:any)=>{setAiReplenish(d);setShowAiReplenish(true)},onError:(e:any)=>message.error('AI 失败')})
  const aiTrendMutation = useMutation({mutationFn: async () => {const {data}=await axios.post('/api/operations-data/ai/trend-commentary',null,{params:{shop_id:currentShop}});return data},onSuccess:(d:any)=>{setAiTrend(d);setShowAiTrend(true)},onError:(e:any)=>message.error('AI 失败')})

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['dashboard-metrics', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/dashboard/metrics', { params: { shop_id: currentShop } })
      return data
    },
  })

  const { data: stocks, isLoading: stocksLoading } = useQuery({
    queryKey: ['analytics-stocks', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/analytics/stocks', { params: { shop_id: currentShop } })
      return data
    },
  })

  const { data: analyticsData, isLoading: analyticsLoading } = useQuery({
    queryKey: ['analytics-data', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/analytics/data', { params: { shop_id: currentShop } })
      return data
    },
  })

  const summaryCards = [
    { title: '总浏览量', value: metrics?.total_views ?? metrics?.views ?? 0, icon: <RiseOutlined />, color: '#1677FF' },
    { title: '总访客', value: metrics?.total_visitors ?? metrics?.visitors ?? 0, icon: <TeamOutlined />, color: '#22c55e' },
    { title: '转化率', value: metrics?.conversion_rate ? `${(metrics.conversion_rate * 100).toFixed(1)}%` : '—', icon: <RiseOutlined />, color: '#f59e0b' },
    { title: '客单价', value: metrics?.avg_order_value ? formatPrice(metrics.avg_order_value, 'RUB') : '—', icon: <StockOutlined />, color: '#ef4444' },
  ]

  const stockColumns = [
    { title: '商品', dataIndex: 'product_name', key: 'product_name', width: 200 },
    { title: 'SKU', dataIndex: 'sku', key: 'sku', width: 140 },
    { title: 'FBO 库存', dataIndex: 'stock_fbo', key: 'stock_fbo', width: 100 },
    { title: 'FBS 库存', dataIndex: 'stock_fbs', key: 'stock_fbs', width: 100 },
    { title: '在途', dataIndex: 'in_transit', key: 'in_transit', width: 80 },
    {
      title: '状态', key: 'status', width: 100,
      render: (_: any, r: any) => {
        const total = (r.stock_fbo || 0) + (r.stock_fbs || 0)
        return total <= 0 ? <Tag color="red">缺货</Tag> : total < 10 ? <Tag color="orange">低库存</Tag> : <Tag color="green">正常</Tag>
      },
    },
  ]

  const analyticsColumns = [
    { title: '指标', dataIndex: 'metric', key: 'metric', width: 160 },
    { title: '当前值', dataIndex: 'current', key: 'current', width: 120 },
    { title: '上期值', dataIndex: 'previous', key: 'previous', width: 120 },
    {
      title: '变化', key: 'change', width: 100,
      render: (_: any, r: any) => {
        if (!r.current || !r.previous) return '—'
        const change = ((r.current - r.previous) / r.previous * 100).toFixed(1)
        const isUp = Number(change) >= 0
        return (
          <span style={{ color: isUp ? '#22c55e' : '#ef4444' }}>
            {isUp ? <RiseOutlined /> : <FallOutlined />} {Math.abs(Number(change))}%
          </span>
        )
      },
    },
  ]

  const stockItems = stocks?.stocks || stocks?.items || []
  const analyticsItems = analyticsData?.metrics || analyticsData?.items || []

  return (
    <div>
      <PageHeader title="运营数据"
        actions={<Space><Tooltip title="AI 补货建议"><Button size="small" icon={<RobotOutlined />} onClick={() => aiReplenishMutation.mutate()} loading={aiReplenishMutation.isPending}>补货建议</Button></Tooltip><Tooltip title="AI 趋势评述"><Button size="small" icon={<RobotOutlined />} onClick={() => aiTrendMutation.mutate()} loading={aiTrendMutation.isPending}>趋势评述</Button></Tooltip></Space>} subtitle="库存分析与指标看板" />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {summaryCards.map((card) => (
          <Col key={card.title} xs={24} sm={12} lg={6}>
            <Card loading={metricsLoading} size="small" hoverable>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Statistic title={card.title} value={card.value} />
                <div style={{ fontSize: 24, color: card.color }}>{card.icon}</div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Tabs
        items={[
          {
            key: 'stocks',
            label: '库存分析',
            children: (
              <Card size="small">
                <Table
                  dataSource={stockItems}
                  rowKey={(r) => r.product_id || r.sku}
                  loading={stocksLoading}
                  size="small"
                  pagination={{ pageSize: 20, showTotal: (t: number) => `共 ${t} 条` }}
                  columns={stockColumns}
                />
              </Card>
            ),
          },
          {
            key: 'trends',
            label: '指标趋势',
            children: (
              <Card size="small">
                <Table
                  dataSource={analyticsItems}
                  rowKey={(r, i) => r.metric || String(i)}
                  loading={analyticsLoading}
                  size="small"
                  pagination={false}
                  columns={analyticsColumns}
                />
              </Card>
            ),
          },
        ]}
      />
      <Modal title="AI 补货建议" open={showAiReplenish} onCancel={()=>setShowAiReplenish(false)} footer={null} width={500}>{aiReplenish?.urgent?.length>0?<div>{aiReplenish.urgent.map((u:any,i:number)=><Alert key={i} message={`${u.name}: 补${u.suggested_replenish}件`} description={u.reason} type="warning" style={{marginBottom:8}}/>)}</div>:<p>无需紧急补货</p>}</Modal>
      <Modal title="AI 趋势评述" open={showAiTrend} onCancel={()=>setShowAiTrend(false)} footer={null} width={400}>{aiTrend&&<div><Typography.Text>{aiTrend.commentary}</Typography.Text><Tag style={{marginTop:8}}>{aiTrend.direction}</Tag></div>}</Modal>
    </div>
  )
}
