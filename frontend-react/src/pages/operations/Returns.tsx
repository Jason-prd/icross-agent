import { useState } from 'react'
import { Card, Segmented, Space, Button, Modal, Descriptions, message, Popconfirm, Alert, Tooltip, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, RollbackOutlined, RobotOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import StatusTag from '../../components/StatusTag'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { formatPrice } from '../../utils/currency'
import axios from 'axios'

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

export default function Returns() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [tab, setTab] = useState('fbo')
  const [detailId, setDetailId] = useState<string | null>(null)
  const [aiDecisionResult, setAiDecisionResult] = useState<any>(null)
  const [showAiDecision, setShowAiDecision] = useState(false)

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

  const aiDecisionMutation = useMutation({
    mutationFn: async (returnId: string) => {
      const { data } = await axios.post(`/api/returns/${returnId}/ai/decision`, null, { params: { shop_id: currentShop } })
      return data
    },
    onSuccess: (data: any) => { setAiDecisionResult(data); setShowAiDecision(true) },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 分析失败'),
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
      key: 'actions', title: '操作', width: 290, fixed: 'right' as const,
      render: (_: any, record: ReturnItem) => (
        <Space size="small">
          <Button size="small" onClick={() => setDetailId(record.return_id)}>详情</Button>
          <Tooltip title="AI 分析退货决策"><Button size="small" icon={<RobotOutlined />} loading={aiDecisionMutation.isPending} onClick={() => aiDecisionMutation.mutate(record.return_id)} /></Tooltip>
          <Popconfirm title="确认验收此退货？" onConfirm={() => acceptMutation.mutate(record.return_id)}>
            <Button size="small" type="primary" icon={<CheckCircleOutlined />}>验收</Button>
          </Popconfirm>
          <Popconfirm title="确认拒绝此退货？" onConfirm={() => rejectMutation.mutate({ id: record.return_id, comment: 'seller rejected' })}>
            <Button size="small" danger icon={<CloseCircleOutlined />}>拒绝</Button>
          </Popconfirm>
          <Button size="small" icon={<RollbackOutlined />} onClick={() => refundMutation.mutate(record.return_id)}>退款</Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <PageHeader title="退货管理" subtitle="处理退货与退款" />

      <Card size="small" style={{ marginBottom: 16 }}>
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

      <Modal title="AI 退货决策" open={showAiDecision} onCancel={() => setShowAiDecision(false)} footer={null} width={500}>
        {aiDecisionResult && (
          <div>
            <Alert message={`建议: ${aiDecisionResult.recommendation === 'accept' ? '接受' : aiDecisionResult.recommendation === 'reject' ? '拒绝' : '部分退款'}`} type={aiDecisionResult.recommendation === 'accept' ? 'success' : aiDecisionResult.recommendation === 'reject' ? 'error' : 'warning'} style={{ marginBottom: 12 }} />
            <Typography.Text>{aiDecisionResult.reasoning}</Typography.Text>
            {aiDecisionResult.suggested_refund_amount > 0 && <p style={{ marginTop: 8 }}>建议退款: {aiDecisionResult.suggested_refund_amount} RUB</p>}
            {aiDecisionResult.risks?.length > 0 && <p style={{ marginTop: 4, color: '#ef4444' }}>风险: {aiDecisionResult.risks.join(', ')}</p>}
          </div>
        )}
      </Modal>

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
    </div>
  )
}
