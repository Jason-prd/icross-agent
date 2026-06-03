import { useState } from 'react'
import { Card, Tabs, Space, Button, Tag, message, Modal, Typography, Alert, Tooltip } from 'antd'
import { PlayCircleOutlined, PauseCircleOutlined, BarChartOutlined, RobotOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import StatusTag from '../../components/StatusTag'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { formatPrice } from '../../utils/currency'
import axios from 'axios'

interface Campaign {
  id: string
  name: string
  status: string
  type: string
  daily_budget: number
  total_budget: number
  start_date: string
  end_date: string
  impressions: number
  clicks: number
  spent: number
}

interface Action {
  id: string
  title: string
  type: string
  status: string
  begin_at: string
  end_at: string
  discount: string
}

function CampaignsTab({ currentShop }: { currentShop: string }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['ad-campaigns', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/ad/campaigns', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const [aiResult, setAiResult] = useState<any>(null)
  const [showAi, setShowAi] = useState(false)

  const aiMutation = useMutation({
    mutationFn: async (campaignId: string) => {
      const { data } = await axios.post(`/api/marketing/ai/analyze-campaign/${campaignId}`, null, { params: { shop_id: currentShop } })
      return data
    },
    onSuccess: (data: any) => { setAiResult(data); setShowAi(true) },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 分析失败'),
  })

  const toggleMutation = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: string }) => {
      await axios.post(`/api/ozon/ad/campaigns/${id}`, { action, shop_id: currentShop })
    },
    onSuccess: () => { message.success('操作成功'); queryClient.invalidateQueries({ queryKey: ['ad-campaigns'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const campaigns: Campaign[] = data?.campaigns || data?.items || []
  const total = data?.total || 0

  return (
    <>
    <DataTable
      columns={[
        { key: 'name', title: '活动名称', dataIndex: 'name', width: 200 },
        { key: 'status', title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
        { key: 'type', title: '类型', dataIndex: 'type', width: 100 },
        { key: 'daily_budget', title: '日预算', dataIndex: 'daily_budget', width: 110, render: (v: number) => formatPrice(v, 'RUB') },
        { key: 'spent', title: '已花费', dataIndex: 'spent', width: 110, render: (v: number) => formatPrice(v, 'RUB') },
        { key: 'impressions', title: '展示', dataIndex: 'impressions', width: 90 },
        { key: 'clicks', title: '点击', dataIndex: 'clicks', width: 80 },
        { key: 'start_date', title: '开始', dataIndex: 'start_date', width: 190, render: (v: string) => v ? new Date(v).toLocaleDateString('zh-CN') : '—' },
        {
          key: 'actions', title: '操作', width: 190,
          render: (_: any, record: Campaign) => (
            <Space size="small">
              <Tooltip title="AI 分析"><Button size="small" icon={<RobotOutlined />} loading={aiMutation.isPending} onClick={() => aiMutation.mutate(record.id)} /></Tooltip>
              <Button
                size="small"
                icon={record.status === 'running_campaign' ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                onClick={() => toggleMutation.mutate({ id: record.id, action: record.status === 'running_campaign' ? 'pause' : 'resume' })}
              >
                {record.status === 'running_campaign' ? '暂停' : '启用'}
              </Button>
            </Space>
          ),
        },
      ]}
      data={campaigns}
      total={total}
      loading={isLoading}
      current={page}
      pageSize={20}
      onChange={(p) => setPage(p)}
      emptyText="暂无广告活动"
    />
      <Modal title="AI 广告分析" open={showAi} onCancel={() => setShowAi(false)} footer={null} width={520}>
        {aiResult && (
          <div>
            <Alert message={`${aiResult.title} — 评分: ${aiResult.score}/100`} type={aiResult.score >= 70 ? 'success' : aiResult.score >= 40 ? 'warning' : 'error'} style={{marginBottom:12}} />
            <Typography.Text>{aiResult.analysis}</Typography.Text>
            {aiResult.suggestions?.length > 0 && <ul style={{marginTop:8}}>{aiResult.suggestions.map((s:any,i:number)=><li key={i}>{s.action}: {s.expected_impact}</li>)}</ul>}
            <p style={{marginTop:8}}><strong>预算建议:</strong> {aiResult.budget_recommendation}</p>
          </div>
        )}
      </Modal>
    </>
  )
}

function ActionsTab({ currentShop }: { currentShop: string }) {
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['ozon-actions', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/actions', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const actions: Action[] = data?.actions || data?.items || []
  const total = data?.total || 0

  return (
    <DataTable
      columns={[
        { key: 'title', title: '活动名称', dataIndex: 'title', width: 220 },
        { key: 'type', title: '类型', dataIndex: 'type', width: 100 },
        { key: 'status', title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
        { key: 'discount', title: '折扣', dataIndex: 'discount', width: 100 },
        { key: 'begin_at', title: '开始', dataIndex: 'begin_at', width: 190, render: (v: string) => v ? new Date(v).toLocaleDateString('zh-CN') : '—' },
        { key: 'end_at', title: '结束', dataIndex: 'end_at', width: 190, render: (v: string) => v ? new Date(v).toLocaleDateString('zh-CN') : '—' },
      ]}
      data={actions}
      total={total}
      loading={isLoading}
      current={page}
      pageSize={20}
      onChange={(p) => setPage(p)}
      emptyText="暂无可用活动"
    />
  )
}

export default function Marketing() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  return (
    <div>
      <PageHeader title="营销广告" subtitle="广告活动与平台促销" />
      <Tabs
        items={[
          { key: 'campaigns', label: '广告活动', children: <CampaignsTab currentShop={currentShop} /> },
          { key: 'actions', label: '平台活动', children: <ActionsTab currentShop={currentShop} /> },
        ]}
      />
    </div>
  )
}
