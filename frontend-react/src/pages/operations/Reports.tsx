import { useState } from 'react'
import { Card, Row, Col, Button, Select, message, Table, Tag, Space, Modal, Typography } from 'antd'
import { FileTextOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import StatusTag from '../../components/StatusTag'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

const { Text } = Typography

const reportTypes = [
  { value: 'products', label: '商品报表' },
  { value: 'orders', label: '订单报表' },
  { value: 'finance', label: '财务报表' },
  { value: 'stocks', label: '库存报表' },
  { value: 'analytics', label: '分析报表' },
]

interface Report {
  id: string
  type: string
  status: string
  created_at: string
  completed_at?: string
  file_url?: string
}

export default function Reports() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [generateType, setGenerateType] = useState('products')
  const [generating, setGenerating] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['reports', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/reports', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const generateMutation = useMutation({
    mutationFn: async () => {
      setGenerating(true)
      const { data } = await axios.post('/api/reports/generate', { report_type: generateType, shop_id: currentShop })
      return data
    },
    onSuccess: () => {
      message.success('报表生成任务已提交，请稍后刷新查看')
      queryClient.invalidateQueries({ queryKey: ['reports'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '生成失败'),
    onSettled: () => setGenerating(false),
  })

  const reports: Report[] = data?.reports || data?.items || []
  const total = data?.total || 0

  const handleDownload = async (reportId: string) => {
    try {
      const { data: blob } = await axios.get(`/api/reports/${reportId}/download`, { responseType: 'blob' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `report-${reportId}.csv`
      a.click()
      URL.revokeObjectURL(url)
      message.success('下载已开始')
    } catch {
      message.error('下载失败')
    }
  }

  const columns = [
    { key: 'id', title: '报表 ID', dataIndex: 'id', width: 180 },
    {
      key: 'type', title: '类型', dataIndex: 'type', width: 120,
      render: (v: string) => {
        const t = reportTypes.find(r => r.value === v)
        return t?.label || v
      },
    },
    { key: 'status', title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
    { key: 'created_at', title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    { key: 'completed_at', title: '完成时间', dataIndex: 'completed_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
    {
      key: 'actions', title: '操作', width: 100,
      render: (_: any, record: Report) => (
        <Button
          size="small"
          icon={<DownloadOutlined />}
          disabled={record.status !== 'completed'}
          onClick={() => handleDownload(record.id)}
        >
          下载
        </Button>
      ),
    },
  ]

  return (
    <div>
      <PageHeader title="报表中心" subtitle="生成和下载运营报表" />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={8}>
            <Text strong>生成新报表</Text>
          </Col>
          <Col xs={12} sm={8}>
            <Select value={generateType} onChange={setGenerateType} style={{ width: '100%' }}>
              {reportTypes.map((t) => (
                <Select.Option key={t.value} value={t.value}>{t.label}</Select.Option>
              ))}
            </Select>
          </Col>
          <Col xs={12} sm={8}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => generateMutation.mutate()}
              loading={generating}
            >
              生成报表
            </Button>
          </Col>
        </Row>
      </Card>

      <Card title="历史报表" size="small">
        <Table
          dataSource={reports}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{
            current: page,
            total,
            pageSize: 20,
            onChange: setPage,
            showTotal: (t: number) => `共 ${t} 条`,
          }}
          columns={columns}
        />
      </Card>
    </div>
  )
}
