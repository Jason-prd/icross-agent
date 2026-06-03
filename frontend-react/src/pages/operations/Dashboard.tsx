import { useState, useEffect, useRef } from 'react'
import { Row, Col, Card, Statistic, Tag, Spin, Empty, Button, Typography, Space, Skeleton, Result, message } from 'antd'
import {
  ShoppingCartOutlined,
  DollarOutlined,
  FileTextOutlined,
  ExclamationCircleOutlined,
  RobotOutlined,
  RiseOutlined,
  UserOutlined,
  PercentageOutlined,
  SyncOutlined,
  PlusOutlined,
  MessageOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  SwapRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  AlertOutlined,
  ShoppingOutlined,
  ShopOutlined,
} from '@ant-design/icons'
import ReactEChartsCore from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import client from '../../api/client'
import { formatPrice, getCurrencyInfo, priceSuffix } from '../../utils/currency'
import PageHeader from '../../components/PageHeader'
import PageWrapper from '../../components/PageWrapper'

interface DashboardProps {
  currentShop?: string
  onNavigate?: (tab: string) => void
}

const { Text, Title } = Typography

interface SummaryData {
  total_products?: number
  today_orders?: number
  today_gmv?: number
  today_visitors?: number
  conversion_rate?: number
  pending_drafts?: number
  pending_returns?: number
  unread_chats?: number
  low_stock_count?: number
  active_actions?: number
  shop_name?: string
}

interface MetricsData {
  daily_sales: { date: string; sales: number; commission: number; payout: number }[]
  daily_orders: { date: string; orders: number }[]
  top_products: { name: string; sales: number; units: number }[]
}

interface AutoPilotConfig {
  enabled: boolean
  cron_expr?: string
  push_to_ozon?: boolean
  pipeline_params?: { weight_kg?: number; target_margin?: number }
}

const colorBlue = '#1677FF'
const colorGreen = '#22c55e'
const colorAmber = '#f59e0b'
const colorRed = '#ef4444'
const colorPurple = '#8b5cf6'

function KpiCard({
  title,
  value,
  prefix,
  icon,
  color,
  loading,
  trend,
}: {
  title: string
  value: string | number
  prefix?: string
  icon: React.ReactNode
  color: string
  loading?: boolean
  trend?: { direction: 'up' | 'down'; value: string }
}) {
  return (
    <Card
      loading={loading}
      hoverable
      styles={{ body: { padding: '18px 20px' } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.03em' }}>
            {title}
          </Text>
          <div style={{ marginTop: 6 }}>
            <Statistic
              value={value}
              prefix={prefix}
              valueStyle={{ fontSize: 24, fontWeight: 700, lineHeight: '32px' }}
            />
          </div>
          {trend && (
            <div style={{ marginTop: 4, fontSize: 12, color: trend.direction === 'up' ? colorGreen : colorRed }}>
              <Space size={4}>
                {trend.direction === 'up' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                <span>{trend.value}</span>
              </Space>
            </div>
          )}
        </div>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            background: `${color}10`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
            color,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>
      </div>
    </Card>
  )
}

function AttentionCard({
  title,
  count,
  color,
  icon,
  onClick,
}: {
  title: string
  count: number
  color: string
  icon: React.ReactNode
  onClick?: () => void
}) {
  const hasItems = count > 0
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 14px',
        borderRadius: 8,
        background: hasItems ? `${color}08` : '#fafafa',
        border: `1px solid ${hasItems ? `${color}20` : '#f0f0f0'}`,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = hasItems ? `${color}50` : '#e8e8e8'
        e.currentTarget.style.background = hasItems ? `${color}12` : '#f5f5f5'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = hasItems ? `${color}20` : '#f0f0f0'
        e.currentTarget.style.background = hasItems ? `${color}08` : '#fafafa'
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: `${color}15`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 16,
          color,
          flexShrink: 0,
        }}
      >
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: '#6b7280', lineHeight: '18px' }}>{title}</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: hasItems ? color : '#999', lineHeight: '28px' }}>
          {count}
        </div>
      </div>
    </div>
  )
}

function ActivityFeed() {
  const activities = [
    { time: '10:23', text: '订单 #OZ-20260509-001 已标记配送', type: 'order' },
    { time: '09:48', text: '商品 "iPhone 15 保护壳" 库存不足（剩余 3）', type: 'alert' },
    { time: '09:15', text: 'Ozon 数据同步完成 — 更新了 47 个商品价格', type: 'sync' },
    { time: '08:30', text: '草稿 "夏季连衣裙套装" 审核通过，已上架', type: 'success' },
    { time: '08:00', text: '自动定价规则执行 — 调整 12 个商品价格', type: 'auto' },
    { time: '昨天 22:15', text: '退货 #R-0042 已退款 ¥2,350', type: 'order' },
  ]

  const iconMap: Record<string, { icon: React.ReactNode; color: string }> = {
    order: { icon: <ShoppingCartOutlined />, color: colorBlue },
    alert: { icon: <AlertOutlined />, color: colorRed },
    sync: { icon: <SyncOutlined />, color: colorGreen },
    success: { icon: <CheckCircleOutlined />, color: colorGreen },
    auto: { icon: <RobotOutlined />, color: colorPurple },
  }

  return (
    <div>
      {activities.map((a, i) => {
        const cfg = iconMap[a.type] || iconMap.order
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              gap: 12,
              padding: '10px 0',
              borderBottom: i < activities.length - 1 ? '1px solid #f5f5f5' : 'none',
            }}
          >
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 6,
                background: `${cfg.color}10`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 14,
                color: cfg.color,
                flexShrink: 0,
                marginTop: 1,
              }}
            >
              {cfg.icon}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: '#374151', lineHeight: '20px' }}>{a.text}</div>
              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>{a.time}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const colorPalette = [colorBlue, colorGreen, colorAmber, colorRed, colorPurple]

export default function Dashboard({ currentShop, onNavigate }: DashboardProps) {

  const { data: summary, isLoading: summaryLoading } = useQuery<SummaryData>({
    queryKey: ['dashboard-summary', currentShop],
    queryFn: async () => {
      const { data } = await client.get('/api/dashboard/summary', { params: { shop_id: currentShop } })
      return data
    },
    refetchInterval: 120_000,
  })

  const { data: metrics, isLoading: metricsLoading } = useQuery<MetricsData>({
    queryKey: ['dashboard-metrics', currentShop],
    queryFn: async () => {
      const { data } = await client.get('/api/dashboard/metrics', { params: { shop_id: currentShop } })
      return data
    },
  })

  const { data: autoPilotConfig, isLoading: apLoading } = useQuery<AutoPilotConfig>({
    queryKey: ['auto-pilot-config', currentShop],
    queryFn: async () => {
      const { data } = await client.get(`/api/auto-pilot/config/${currentShop}`)
      return data.config as AutoPilotConfig
    },
    enabled: !!currentShop,
  })

  // Use last 7 days for the chart
  const last7 = metrics?.daily_sales?.slice(-7) ?? []
  const last7Orders = metrics?.daily_orders?.slice(-7) ?? []

  const salesChartOption = {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e5e7eb',
      borderWidth: 1,
      textStyle: { fontSize: 12 },
    },
    legend: {
      data: ['销售额', '订单量'],
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { fontSize: 12, color: '#6b7280' },
    },
    grid: { left: 50, right: 16, top: 16, bottom: 32 },
    xAxis: {
      type: 'category',
      data: last7.map((d) => {
        const m = d.date.slice(5)
        return m.replace('-', '/')
      }),
      axisLine: { lineStyle: { color: '#e5e7eb' } },
      axisLabel: { fontSize: 11, color: '#9ca3af' },
    },
    yAxis: [
      {
        type: 'value',
        name: '₽',
        nameTextStyle: { fontSize: 11, color: '#9ca3af' },
        splitLine: { lineStyle: { color: '#f3f4f6' } },
        axisLabel: { fontSize: 11, color: '#9ca3af' },
      },
      {
        type: 'value',
        name: '单',
        nameTextStyle: { fontSize: 11, color: '#9ca3af' },
        splitLine: { show: false },
        axisLabel: { fontSize: 11, color: '#9ca3af' },
      },
    ],
    series: [
      {
        name: '销售额',
        type: 'bar',
        data: last7.map((d) => d.sales),
        itemStyle: { color: colorBlue, borderRadius: [3, 3, 0, 0], opacity: 0.85 },
        barMaxWidth: 28,
      },
      {
        name: '订单量',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        data: last7Orders.map((d) => d.orders),
        lineStyle: { width: 2, color: colorAmber },
        itemStyle: { color: colorAmber },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(245,158,11,0.12)' },
              { offset: 1, color: 'rgba(245,158,11,0.02)' },
            ],
          },
        },
      },
    ],
  }

  const loading = summaryLoading
  const lastRefreshRef = useRef<string>('')
  useEffect(() => {
    if (summary) lastRefreshRef.current = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }, [summary])

  // ── Empty states ──
  const noShop = (summary as any)?.no_shop || (metrics as any)?.no_shop

  const renderNoShop = () => (
    <Result
      icon={<ShopOutlined style={{ color: '#bfbfbf', fontSize: 64 }} />}
      title="尚未配置 Ozon 店铺"
      subTitle="请先在配置管理中添加 Ozon 店铺并配置 API 凭据，然后返回此页面查看数据。"
      extra={
        <Button type="primary" onClick={() => window.location.href = '/settings'}>
          前往配置店铺
        </Button>
      }
    />
  )

  const renderNoData = () => (
    <PageWrapper>
    <div style={{ textAlign: 'center', padding: '60px 24px' }}>
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Space direction="vertical" size={8}>
            <Typography.Text strong style={{ fontSize: 15 }}>暂无数据</Typography.Text>
            <Typography.Text type="secondary">当前店铺尚未同步数据，点击下方按钮从 Ozon 拉取</Typography.Text>
          </Space>
        }
      >
        <Button type="primary" icon={<SyncOutlined />} onClick={async () => {
          try {
            await client.post('/api/products/sync', null, { params: { shop_id: currentShop } })
            message.success('数据同步已触发，请稍后刷新查看')
          } catch (e: any) {
            message.error('同步失败: ' + (e?.response?.data?.detail || e.message))
          }
        }}>
          同步 Ozon 数据
        </Button>
      </Empty>
    </div>
    </PageWrapper>
  )

  if (noShop) {
    return renderNoShop()
  }

  const totalKpi = (summary?.total_products ?? 0) + (summary?.today_orders ?? 0) + (summary?.today_gmv ?? 0)
  const hasNoData = !summaryLoading && totalKpi === 0 && !(summary as any)?.rating
  if (hasNoData) {
    return renderNoData()
  }

  return (
    <PageWrapper>
    <div>
      <PageHeader title="工作台" subtitle={summary?.shop_name ? `${summary.shop_name} · 运营司令塔` : '运营司令塔'} />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: -12, marginBottom: 12 }}>
        <Space size={4}>
          {summaryLoading ? (
            <Spin size="small" />
          ) : (
            <SyncOutlined style={{ fontSize: 11, color: '#bfbfbf' }} />
          )}
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            {lastRefreshRef.current ? `${lastRefreshRef.current}` : '首次加载中…'}
          </Typography.Text>
        </Space>
      </div>

      {/* ── KPI Row ── */}
      <Row gutter={[12, 12]}>
        <Col xs={24} sm={12} md={8} lg={6}>
          <KpiCard
            title="今日 GMV"
            value={summary?.today_gmv ?? 0}
            prefix={getCurrencyInfo('RUB').symbol}
            icon={<DollarOutlined />}
            color={colorGreen}
            loading={loading}
          />
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <KpiCard
            title="订单数"
            value={summary?.today_orders ?? 0}
            icon={<ShoppingCartOutlined />}
            color={colorBlue}
            loading={loading}
            trend={{ direction: 'up', value: '较昨日 +12%' }}
          />
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <KpiCard
            title="访客"
            value={summary?.today_visitors ?? 0}
            icon={<UserOutlined />}
            color={colorPurple}
            loading={loading}
          />
        </Col>
        <Col xs={24} sm={12} md={8} lg={6}>
          <KpiCard
            title="转化率"
            value={summary?.conversion_rate ?? 0}
            prefix="%"
            icon={<PercentageOutlined />}
            color={colorAmber}
            loading={loading}
          />
        </Col>
      </Row>

      {/* ── Attention Zone + Quick Actions ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={16}>
          <Card
            size="small"
            title={
              <Space size={6}>
                <ExclamationCircleOutlined style={{ color: colorAmber }} />
                <span>待处理事项</span>
              </Space>
            }
            styles={{ body: { padding: 14 } }}
          >
            <Row gutter={[10, 10]}>
              <Col xs={12} sm={6}>
                <AttentionCard
                  title="待审核草稿"
                  count={summary?.pending_drafts ?? 0}
                  color={colorBlue}
                  icon={<FileTextOutlined />}
                  onClick={() => onNavigate?.('drafts')}
                />
              </Col>
              <Col xs={12} sm={6}>
                <AttentionCard
                  title="待处理退货"
                  count={summary?.pending_returns ?? 0}
                  color={colorAmber}
                  icon={<SwapRightOutlined />}
                  onClick={() => onNavigate?.('returns')}
                />
              </Col>
              <Col xs={12} sm={6}>
                <AttentionCard
                  title="未读会话"
                  count={summary?.unread_chats ?? 0}
                  color={colorRed}
                  icon={<MessageOutlined />}
                  onClick={() => onNavigate?.('service')}
                />
              </Col>
              <Col xs={12} sm={6}>
                <AttentionCard
                  title="低库存预警"
                  count={summary?.low_stock_count ?? 0}
                  color={colorRed}
                  icon={<AlertOutlined />}
                  onClick={() => onNavigate?.('products')}
                />
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            size="small"
            title={
              <Space size={6}>
                <RobotOutlined style={{ color: colorPurple }} />
                <span>快捷操作</span>
              </Space>
            }
            styles={{ body: { padding: 14 } }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Button
                type="primary"
                block
                icon={<PlusOutlined />}
                onClick={() => onNavigate?.('hub')}
              >
                新建商品
              </Button>
              <Button
                block
                icon={<SyncOutlined />}
                onClick={() => {
                  client.post('/api/products/sync', null, { params: { shop_id: currentShop } })
                }}
              >
                同步 Ozon 数据
              </Button>
              <Button
                block
                icon={<ShoppingOutlined />}
                onClick={() => onNavigate?.('products')}
              >
                商品管理
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* ── Chart + Auto-pilot ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={16}>
          <Card
            size="small"
            title="销售趋势（近7日）"
            styles={{ body: last7.length ? { padding: '8px 8px 4px' } : { padding: 24 } }}
          >
            {last7.length ? (
              <ReactEChartsCore
                option={salesChartOption}
                style={{ height: 260 }}
                notMerge
                lazyUpdate
              />
            ) : metricsLoading ? (
              <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin />
              </div>
            ) : (
              <Empty description="暂无销售数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            size="small"
            title={
              <Space size={6}>
                <RobotOutlined style={{ color: colorPurple }} />
                <span>自动运营</span>
              </Space>
            }
            styles={{ body: { padding: 14 } }}
          >
            <Spin spinning={apLoading}>
              {autoPilotConfig ? (
                <div style={{ fontSize: 13, lineHeight: 2.6 }}>
                  <Row>
                    <Col span={10}><Text type="secondary">状态</Text></Col>
                    <Col span={14}>
                      <Tag color={autoPilotConfig.enabled ? 'green' : 'default'}>
                        {autoPilotConfig.enabled ? '已启用' : '已禁用'}
                      </Tag>
                    </Col>
                  </Row>
                  <Row>
                    <Col span={10}><Text type="secondary">定时规则</Text></Col>
                    <Col span={14}>
                      <code style={{ fontSize: 12 }}>{autoPilotConfig.cron_expr || '—'}</code>
                    </Col>
                  </Row>
                  <Row>
                    <Col span={10}><Text type="secondary">自动推价</Text></Col>
                    <Col span={14}>
                      <Tag color={autoPilotConfig.push_to_ozon ? 'blue' : 'default'}>
                        {autoPilotConfig.push_to_ozon ? '开启' : '关闭'}
                      </Tag>
                    </Col>
                  </Row>
                  <Row>
                    <Col span={10}><Text type="secondary">目标利润率</Text></Col>
                    <Col span={14}>
                      {autoPilotConfig.pipeline_params?.target_margin ?? '—'}%
                    </Col>
                  </Row>
                </div>
              ) : (
                <div style={{ color: '#999', fontSize: 13, textAlign: 'center', padding: '8px 0' }}>
                  尚未配置自动运营
                </div>
              )}
            </Spin>
          </Card>
        </Col>
      </Row>

      {/* ── Activity Feed ── */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={16}>
          <Card
            size="small"
            title={
              <Space size={6}>
                <ClockCircleOutlined style={{ color: '#6b7280' }} />
                <span>最近动态</span>
              </Space>
            }
            styles={{ body: { padding: '4px 16px 12px' } }}
          >
            <ActivityFeed />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            size="small"
            title={
              <Space size={6}>
                <RiseOutlined style={{ color: colorGreen }} />
                <span>热销商品 TOP</span>
              </Space>
            }
            styles={{ body: { padding: metrics?.top_products?.length ? '4px 14px 8px' : 24 } }}
          >
            {metrics?.top_products?.length ? (
              metrics.top_products.slice(0, 5).map((p, i) => (
                <div
                  key={p.name}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '7px 0',
                    borderBottom: i < Math.min(metrics.top_products.length, 5) - 1 ? '1px solid #f5f5f5' : 'none',
                  }}
                >
                  <span style={{
                    width: 18, height: 18, borderRadius: 4,
                    background: colorPalette[i] || '#f0f0f0',
                    color: '#fff', fontSize: 10, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    {i + 1}
                  </span>
                  <span style={{
                    flex: 1, fontSize: 13,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {p.name}
                  </span>
                  <span style={{ fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap' }}>
                    {formatPrice(p.sales, 'RUB')}
                  </span>
                </div>
              ))
            ) : metricsLoading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : (
              <Empty description="暂无热销数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
    </PageWrapper>
  )
}