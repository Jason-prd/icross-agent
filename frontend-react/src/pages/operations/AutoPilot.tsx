import { useState } from 'react'
import { Card, Row, Col, Statistic, Tag, Button, Modal, Descriptions, message, Space, Popconfirm, Table, Switch, InputNumber, Input, Tabs, Form, Alert, Typography, Tooltip } from 'antd'
import { PlayCircleOutlined, PauseCircleOutlined, SettingOutlined, SaveOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import StatusTag from '../../components/StatusTag'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

interface Workflow {
  id: string
  name: string
  status: string
  pipeline_type: string
  created_at: string
  current_step: number
  total_steps: number
}

interface SchedulerJob {
  id: string
  name: string
  task_type: string
  cron_expression: string
  enabled: boolean
  last_run: string
  next_run: string
}

interface AutoPilotConfig {
  enabled: boolean
  cron_expr: string
  push_to_ozon: boolean
  pipeline_params: {
    weight_kg: number
    target_margin: number
  }
}

function ConfigTab({ currentShop }: { currentShop: string }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form] = Form.useForm()

  const { data, isLoading } = useQuery({
    queryKey: ['auto-pilot-config', currentShop],
    queryFn: async () => {
      const { data } = await axios.get(`/api/auto-pilot/config/${currentShop}`)
      return data.config as AutoPilotConfig
    },
  })

  const saveMutation = useMutation({
    mutationFn: async (values: any) => {
      const { data } = await axios.put(`/api/auto-pilot/config/${currentShop}`, {
        enabled: values.enabled,
        cron_expr: values.cron_expr,
        push_to_ozon: values.push_to_ozon,
        pipeline_params: {
          weight_kg: values.weight_kg,
          target_margin: values.target_margin,
        },
      })
      return data
    },
    onSuccess: () => {
      message.success('配置已保存')
      setEditing(false)
      queryClient.invalidateQueries({ queryKey: ['auto-pilot-config'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '保存失败'),
  })

  const toggleMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      const { data } = await axios.post(`/api/auto-pilot/config/${currentShop}/toggle`, { enabled })
      return data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auto-pilot-config'] })
      message.success('已更新')
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  if (isLoading) return <Card loading size="small" />
  const config = data

  return (
    <Card size="small">
      {editing ? (
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            enabled: config?.enabled ?? false,
            cron_expr: config?.cron_expr ?? '0 3 * * *',
            push_to_ozon: config?.push_to_ozon ?? true,
            weight_kg: config?.pipeline_params?.weight_kg ?? 0.5,
            target_margin: config?.pipeline_params?.target_margin ?? 20,
          }}
          onFinish={(values) => saveMutation.mutate(values)}
          style={{ maxWidth: 480 }}
        >
          <Form.Item name="enabled" label="启用自动运营" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="cron_expr" label="定时表达式" rules={[{ required: true, message: '请输入 cron 表达式' }]}>
            <Input placeholder="0 3 * * *" />
          </Form.Item>
          <Form.Item name="push_to_ozon" label="自动推送到 Ozon" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="weight_kg" label="默认重量 (kg)">
            <InputNumber min={0.01} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="target_margin" label="目标利润率 (%)">
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saveMutation.isPending}>保存</Button>
            <Button onClick={() => setEditing(false)}>取消</Button>
          </Space>
        </Form>
      ) : (
        <div>
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <Statistic title="自动运营" value={config?.enabled ? '已启用' : '已禁用'} valueStyle={{ color: config?.enabled ? '#22c55e' : '#999' }} />
            </Col>
            <Col span={12}>
              <Statistic title="定时规则" value={config?.cron_expr || '—'} />
            </Col>
            <Col span={12}>
              <Statistic title="自动推价" value={config?.push_to_ozon ? '开启' : '关闭'} />
            </Col>
            <Col span={12}>
              <Statistic title="目标利润率" value={config?.pipeline_params?.target_margin ? `${config.pipeline_params.target_margin}%` : '—'} />
            </Col>
          </Row>
          <div style={{ marginTop: 16 }}>
            <Space>
              <Button
                type={config?.enabled ? 'default' : 'primary'}
                icon={config?.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                onClick={() => toggleMutation.mutate(!config?.enabled)}
              >
                {config?.enabled ? '停用' : '启用'}
              </Button>
              <Button icon={<SettingOutlined />} onClick={() => setEditing(true)}>编辑配置</Button>
            </Space>
          </div>
        </div>
      )}
    </Card>
  )
}

function WorkflowsTab({ currentShop }: { currentShop: string }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [detailId, setDetailId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['workflows', currentShop, page],
    queryFn: async () => {
      const { data } = await axios.get('/api/workflows', {
        params: { shop_id: currentShop, limit: 20, offset: (page - 1) * 20 },
      })
      return data
    },
  })

  const { data: wfDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['workflow-detail', detailId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/workflows/${detailId}`)
      return data
    },
    enabled: !!detailId,
  })

  const startMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.post(`/api/workflows/${id}/start`)
    },
    onSuccess: () => { message.success('工作流已启动'); queryClient.invalidateQueries({ queryKey: ['workflows'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '启动失败'),
  })

  const workflows = data?.workflows || data?.items || []
  const total = data?.total || 0

  return (
    <>
      <Card size="small">
        <Table
          dataSource={workflows}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{ current: page, total, pageSize: 20, onChange: setPage, showTotal: (t: number) => `共 ${t} 条` }}
          columns={[
            { title: '工作流', dataIndex: 'name', key: 'name', width: 200 },
            { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (v: string) => <StatusTag status={v} /> },
            { title: '类型', dataIndex: 'pipeline_type', key: 'pipeline_type', width: 120 },
            { title: '进度', key: 'progress', width: 80, render: (_: any, r: Workflow) => `${r.current_step || 0}/${r.total_steps || 0}` },
            { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
            {
              title: '操作', key: 'actions', width: 120,
              render: (_: any, record: Workflow) => (
                <Space size="small">
                  <Button size="small" onClick={() => setDetailId(record.id)}>详情</Button>
                  {record.status === 'pending' && (
                    <Popconfirm title="启动此工作流？" onConfirm={() => startMutation.mutate(record.id)}>
                      <Button size="small" type="primary" icon={<PlayCircleOutlined />}>启动</Button>
                    </Popconfirm>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal title="工作流详情" open={!!detailId} onCancel={() => setDetailId(null)} footer={null} width={640}>
        {detailLoading ? <p>加载中…</p> : wfDetail ? (
          <Descriptions column={1} size="small" bordered>
            {(typeof wfDetail === 'object' && 'steps' in wfDetail
              ? Object.entries(wfDetail).filter(([k]) => k !== 'steps')
              : Object.entries(wfDetail)
            ).map(([key, val]) => (
              <Descriptions.Item key={key} label={key}>{String(val ?? '—')}</Descriptions.Item>
            ))}
          </Descriptions>
        ) : <p>无数据</p>}
      </Modal>
    </>
  )
}

function SchedulerTab({ currentShop }: { currentShop: string }) {
  const queryClient = useQueryClient()

  const { data: jobData, isLoading: jobLoading } = useQuery({
    queryKey: ['scheduler-jobs'],
    queryFn: async () => {
      const { data } = await axios.get('/api/scheduler/jobs')
      return data
    },
  })

  const { data: schedulerStatus } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: async () => {
      const { data } = await axios.get('/api/scheduler/status')
      return data
    },
  })

  const toggleJobMutation = useMutation({
    mutationFn: async ({ id, enabled }: { id: string; enabled: boolean }) => {
      await axios.put(`/api/scheduler/jobs/${id}/toggle`, { enabled })
    },
    onSuccess: () => { message.success('已更新'); queryClient.invalidateQueries({ queryKey: ['scheduler-jobs'] }) },
    onError: (e: any) => message.error(e.response?.data?.detail || '操作失败'),
  })

  const jobs: SchedulerJob[] = jobData?.jobs || jobData?.items || []

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12}>
          <Card size="small">
            <Statistic title="调度器" value={schedulerStatus?.running ? '运行中' : '已停止'} valueStyle={{ color: schedulerStatus?.running ? '#22c55e' : '#999' }} />
          </Card>
        </Col>
        <Col xs={24} sm={12}>
          <Card size="small">
            <Statistic title="定时任务" value={jobs.filter(j => j.enabled).length} suffix={`/ ${jobs.length}`} />
          </Card>
        </Col>
      </Row>

      <Card title="定时任务列表" size="small">
        <Table
          dataSource={jobs}
          rowKey="id"
          loading={jobLoading}
          size="small"
          pagination={false}
          columns={[
            { title: '任务名称', dataIndex: 'name', key: 'name', width: 200 },
            { title: '类型', dataIndex: 'task_type', key: 'task_type', width: 120 },
            { title: 'Cron', dataIndex: 'cron_expression', key: 'cron', width: 120 },
            { title: '状态', key: 'enabled', width: 80, render: (_: any, r: SchedulerJob) => r.enabled ? <Tag color="green">已启用</Tag> : <Tag>已禁用</Tag> },
            { title: '上次执行', dataIndex: 'last_run', key: 'last_run', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
            { title: '下次执行', dataIndex: 'next_run', key: 'next_run', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—' },
            {
              title: '操作', key: 'actions', width: 80,
              render: (_: any, r: SchedulerJob) => (
                <Popconfirm title={r.enabled ? '禁用？' : '启用？'} onConfirm={() => toggleJobMutation.mutate({ id: r.id, enabled: !r.enabled })}>
                  <Button size="small" icon={r.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}>
                    {r.enabled ? '禁用' : '启用'}
                  </Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>
    </>
  )
}

export default function AutoPilot() {
  const [aiConfig, setAiConfig] = useState<any>(null); const [showAiConfig, setShowAiConfig] = useState(false)
  const aiConfigMutation = useMutation({mutationFn: async () => {const {data}=await axios.post('/api/auto-pilot/ai/suggest-config',null,{params:{shop_id:currentShop}});return data},onSuccess:(d:any)=>{setAiConfig(d);setShowAiConfig(true)},onError:(e:any)=>message.error('AI 分析失败')})
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  return (
    <div>
      <PageHeader title="自动运营"
        actions={<Tooltip title="AI 配置建议"><Button size="small" icon={<RobotOutlined />} onClick={() => aiConfigMutation.mutate()} loading={aiConfigMutation.isPending}>AI 建议</Button></Tooltip>} subtitle="自动化配置与工作流管理" />
      <Tabs
        items={[
          { key: 'config', label: '运营配置', children: <ConfigTab currentShop={currentShop} /> },
          { key: 'workflows', label: '工作流', children: <WorkflowsTab currentShop={currentShop} /> },
          { key: 'scheduler', label: '定时任务', children: <SchedulerTab currentShop={currentShop} /> },
        ]}
      />
      <Modal title="AI 配置建议" open={showAiConfig} onCancel={()=>setShowAiConfig(false)} footer={null} width={400}>{aiConfig&&<div><Alert message={aiConfig.reasoning} type="info" style={{marginBottom:12}}/><p>推荐cron: {aiConfig.suggested_cron}</p><p>推荐利润率: {aiConfig.suggested_margin}%</p><p>默认重量: {aiConfig.suggested_weight_kg}kg</p><p>推送到Ozon: {aiConfig.push_to_ozon?'是':'否'}</p></div>}</Modal>
    </div>
  )
}
