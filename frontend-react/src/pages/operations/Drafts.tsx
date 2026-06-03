import { useState } from 'react'
import { Card, Button, message, Modal, Input, Descriptions, Space, Typography, Spin, Alert, Tooltip } from 'antd'
import { CheckOutlined, CloseOutlined, RobotOutlined, ThunderboltOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import StatusTag from '../../components/StatusTag'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import { formatPrice } from '../../utils/currency'
import axios from 'axios'

const { TextArea } = Input
const { Text } = Typography

interface Draft {
  id: string
  draft_type: string
  title: string
  price: number
  status: string
  source_url?: string
  created_at: string
  description?: string
  offer_id?: string
  images?: string[]
  reject_reason?: string
}

export default function Drafts() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [selectedDraft, setSelectedDraft] = useState<Draft | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [showReject, setShowReject] = useState(false)
  const [aiCheckResult, setAiCheckResult] = useState<any>(null)
  const [aiCorrectResult, setAiCorrectResult] = useState<any>(null)
  const [showAiCheck, setShowAiCheck] = useState(false)
  const [showAiCorrect, setShowAiCorrect] = useState(false)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['drafts', currentShop, page, pageSize, statusFilter],
    queryFn: async () => {
      const { data } = await axios.get('/api/drafts', {
        params: { shop_id: currentShop, limit: pageSize, offset: (page - 1) * pageSize, status: statusFilter },
      })
      return data
    },
  })

  const approveMutation = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await axios.post(`/api/drafts/${id}/approve`)
      return data
    },
    onSuccess: () => {
      message.success('草稿已通过并提交发布')
      setSelectedDraft(null)
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const aiQualityMutation = useMutation({
    mutationFn: async (draftId: string) => {
      const { data } = await axios.post(`/api/drafts/${draftId}/ai/quality-check`, null, { params: { shop_id: currentShop } })
      return data
    },
    onSuccess: (data: any) => { setAiCheckResult(data); setShowAiCheck(true) },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 检查失败'),
  })

  const aiCorrectMutation = useMutation({
    mutationFn: async (draftId: string) => {
      const { data } = await axios.post(`/api/drafts/${draftId}/ai/correct`, null, { params: { shop_id: currentShop } })
      return data
    },
    onSuccess: (data: any) => { setAiCorrectResult(data); setShowAiCorrect(true) },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 修正失败'),
  })

  const rejectMutation = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
      const { data } = await axios.post(`/api/drafts/${id}/reject`, null, { params: { reason } })
      return data
    },
    onSuccess: () => {
      message.success('已驳回')
      setShowReject(false)
      setSelectedDraft(null)
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const drafts: Draft[] = data?.drafts || data?.items || []
  const total = data?.total || data?.total_count || 0

  const columns = [
    { key: 'title', title: '标题', dataIndex: 'title', width: 300 },
    { key: 'draft_type', title: '类型', dataIndex: 'draft_type', width: 100 },
    { key: 'price', title: '价格', dataIndex: 'price', width: 110, render: (v: number) => formatPrice(v) },
    { key: 'status', title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
    { key: 'created_at', title: '创建时间', dataIndex: 'created_at', width: 170, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    {
      key: 'actions', title: '操作', width: 230,
      render: (_: any, r: Draft) => (
        <Space size="small">
          <Button size="small" type="link" onClick={() => setSelectedDraft(r)}>详情</Button>
          {r.status === 'pending' && (
            <>
              <Tooltip title="AI 质检"><Button size="small" type="link" icon={<RobotOutlined />} loading={aiQualityMutation.isPending} onClick={() => aiQualityMutation.mutate(r.id)} /></Tooltip>
              <Button size="small" type="link" style={{ color: '#22c55e' }} onClick={() => approveMutation.mutate(r.id)}>
                通过
              </Button>
              <Button size="small" type="link" danger onClick={() => { setSelectedDraft(r); setShowReject(true) }}>
                驳回
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="草稿审核"
        breadcrumbs={[{ label: '商品管理' }, { label: '草稿审核' }]}
        actions={
          <Space>
            {['pending', 'approved', 'rejected', 'all'].map((s) => (
              <Button
                key={s}
                size="small"
                type={statusFilter === s ? 'primary' : 'default'}
                onClick={() => { setStatusFilter(s); setPage(1) }}
              >
                {{ pending: '待审核', approved: '已通过', rejected: '已驳回', all: '全部' }[s]}
              </Button>
            ))}
          </Space>
        }
      />

      <DataTable
        columns={columns}
        data={drafts}
        total={total}
        loading={isLoading}
        current={page}
        pageSize={pageSize}
        onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
        onRefresh={refetch}
        emptyText={statusFilter === 'pending' ? '暂无待审核草稿' : '暂无草稿'}
      />

      <Modal title="草稿详情" open={!!selectedDraft && !showReject} onCancel={() => setSelectedDraft(null)} footer={null} width={640}>
        {selectedDraft && (
          <div>
            <Descriptions column={2} size="small" bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="标题" span={2}>{selectedDraft.title}</Descriptions.Item>
              <Descriptions.Item label="价格">{formatPrice(selectedDraft.price)}</Descriptions.Item>
              <Descriptions.Item label="SKU">{selectedDraft.offer_id || '—'}</Descriptions.Item>
              <Descriptions.Item label="状态" span={2}><StatusTag status={selectedDraft.status} /></Descriptions.Item>
              <Descriptions.Item label="来源">{selectedDraft.source_url ? <a href={selectedDraft.source_url} target="_blank">查看</a> : '—'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{new Date(selectedDraft.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
            </Descriptions>
            {selectedDraft.description && (
              <div style={{ marginBottom: 16 }}>
                <Text strong>描述: </Text>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, marginTop: 4 }}>{selectedDraft.description}</div>
              </div>
            )}
            {selectedDraft.reject_reason && (
              <div><Text strong>驳回原因: </Text><Text type="danger">{selectedDraft.reject_reason}</Text></div>
            )}
            {selectedDraft.status === 'pending' && (
              <Space style={{ marginTop: 16 }}>
                <Tooltip title="AI 自动修正"><Button icon={<ThunderboltOutlined />} onClick={() => aiCorrectMutation.mutate(selectedDraft.id)} loading={aiCorrectMutation.isPending}>AI 修正</Button></Tooltip>
                <Button type="primary" icon={<CheckOutlined />} onClick={() => approveMutation.mutate(selectedDraft.id)}>通过并发布</Button>
                <Button danger icon={<CloseOutlined />} onClick={() => setShowReject(true)}>驳回</Button>
              </Space>
            )}
          </div>
        )}
      </Modal>

      <Modal title="AI 质量检查" open={showAiCheck} onCancel={() => setShowAiCheck(false)} footer={null} width={500}>
        {aiCheckResult && (
          <div>
            <Alert message={`质量评分: ${aiCheckResult.score}/100`} type={aiCheckResult.score >= 80 ? 'success' : aiCheckResult.score >= 60 ? 'warning' : 'error'} style={{ marginBottom: 12 }} />
            <Text>{aiCheckResult.summary}</Text>
            {aiCheckResult.issues?.length > 0 && (
              <ul style={{ marginTop: 8 }}>
                {aiCheckResult.issues.map((iss: any, i: number) => (
                  <li key={i}><Text type={iss.severity === 'error' ? 'danger' : 'warning'}>{iss.field}: {iss.message}</Text> — {iss.suggestion}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Modal>

      <Modal title="AI 自动修正" open={showAiCorrect} onCancel={() => setShowAiCorrect(false)} footer={null} width={500}>
        {aiCorrectResult && (
          <div>
            {aiCorrectResult.changes?.length > 0 && (
              <ul style={{ marginBottom: 12 }}>
                {aiCorrectResult.changes.map((c: string, i: number) => <li key={i}>{c}</li>)}
              </ul>
            )}
            <Text strong>修正后标题: </Text><Text>{aiCorrectResult.corrected_title}</Text>
            <div style={{ marginTop: 8 }}><Text strong>修正后描述: </Text><Text>{aiCorrectResult.corrected_description?.slice(0, 200)}</Text></div>
          </div>
        )}
      </Modal>

      <Modal
        title="驳回草稿"
        open={showReject}
        onCancel={() => { setShowReject(false); setRejectReason('') }}
        onOk={() => selectedDraft && rejectMutation.mutate({ id: selectedDraft.id, reason: rejectReason })}
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        confirmLoading={rejectMutation.isPending}
      >
        <TextArea
          rows={3}
          placeholder="输入驳回原因…"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  )
}
