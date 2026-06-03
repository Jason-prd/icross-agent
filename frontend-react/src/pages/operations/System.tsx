import { useState } from 'react'
import { Card, Row, Col, Statistic, Table, Tag, Tabs, Badge, Typography } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, SyncOutlined, ApiOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import StatusTag from '../../components/StatusTag'
import { useQuery } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

const { Text } = Typography

export default function System() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const [taskPage, setTaskPage] = useState(1)
  const [logPage, setLogPage] = useState(1)

  const { data: tasks, isLoading: tasksLoading } = useQuery({
    queryKey: ['tasks', taskPage],
    queryFn: async () => {
      const { data } = await axios.get('/api/tasks', {
        params: { limit: 20, offset: (taskPage - 1) * 20 },
      })
      return data
    },
  })

  const { data: syncLogs, isLoading: logsLoading } = useQuery({
    queryKey: ['sync-logs', currentShop, logPage],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon/sync-logs', {
        params: { shop_id: currentShop, limit: 20, offset: (logPage - 1) * 20 },
      })
      return data
    },
  })

  const { data: sellerInfo, isLoading: sellerLoading } = useQuery({
    queryKey: ['seller-info', currentShop],
    queryFn: async () => {
      const { data } = await axios.get(`/api/ozon/seller-info/${currentShop}`)
      return data
    },
  })

  const { data: taskStats } = useQuery({
    queryKey: ['task-stats'],
    queryFn: async () => {
      const { data } = await axios.get('/api/tasks/stats/summary')
      return data
    },
  })

  const taskList = tasks?.tasks || tasks?.items || []
  const taskTotal = tasks?.total || 0
  const logList = syncLogs?.logs || syncLogs?.items || []
  const logTotal = syncLogs?.total || 0

  return (
    <div>
      <PageHeader title="系统设置" subtitle="运营系统状态与日志" />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small" loading={sellerLoading}>
            <Statistic
              title="店铺状态"
              value={sellerInfo?.status || sellerInfo?.state || '正常'}
              valueStyle={{ color: '#22c55e' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title="待处理任务" value={taskStats?.pending ?? 0} valueStyle={{ color: '#f59e0b' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title="运行中任务" value={taskStats?.running ?? 0} valueStyle={{ color: '#1677FF' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card size="small">
            <Statistic title="失败任务" value={taskStats?.failed ?? 0} valueStyle={{ color: '#ef4444' }} />
          </Card>
        </Col>
      </Row>

      <Tabs
        items={[
          {
            key: 'tasks',
            label: '任务队列',
            children: (
              <Card size="small">
                <Table
                  dataSource={taskList}
                  rowKey="id"
                  loading={tasksLoading}
                  size="small"
                  pagination={{
                    current: taskPage,
                    total: taskTotal,
                    pageSize: 20,
                    onChange: setTaskPage,
                    showTotal: (t: number) => `共 ${t} 条`,
                  }}
                  columns={[
                    { title: '任务 ID', dataIndex: 'id', key: 'id', width: 180 },
                    { title: '类型', dataIndex: 'type', key: 'type', width: 120 },
                    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
                    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
                    { title: '完成时间', dataIndex: 'completed_at', key: 'completed_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
                    {
                      title: '错误信息', dataIndex: 'error', key: 'error', width: 200,
                      render: (v: string) => v ? <Text type="danger" ellipsis style={{ maxWidth: 180 }}>{v}</Text> : '—',
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: 'logs',
            label: '同步日志',
            children: (
              <Card size="small">
                <Table
                  dataSource={logList}
                  rowKey={(r: any, i) => r?.id || String(i)}
                  loading={logsLoading}
                  size="small"
                  pagination={{
                    current: logPage,
                    total: logTotal,
                    pageSize: 20,
                    onChange: setLogPage,
                    showTotal: (t: number) => `共 ${t} 条`,
                  }}
                  columns={[
                    { title: '操作', dataIndex: 'action', key: 'action', width: 140 },
                    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
                    { title: '详情', dataIndex: 'detail', key: 'detail', width: 260 },
                    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: 'info',
            label: '店铺信息',
            children: (
              <Card size="small" loading={sellerLoading}>
                <Table
                  dataSource={sellerInfo ? [sellerInfo] : []}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  columns={Object.keys(sellerInfo || {}).map((key) => ({
                    title: key,
                    dataIndex: key,
                    key,
                    render: (v: any) => {
                      if (typeof v === 'object') return JSON.stringify(v)
                      if (key.toLowerCase().includes('status') || key.toLowerCase().includes('state')) return <StatusTag status={String(v)} />
                      return String(v ?? '—')
                    },
                  }))}
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  )
}
