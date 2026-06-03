import { Card, Row, Col, Tag, Button, Typography } from 'antd'
import {
  DollarOutlined,
  RobotOutlined,
  SettingOutlined,
  FileTextOutlined,
  BookOutlined,
  CalculatorOutlined,
  RightOutlined,
} from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'

const { Text } = Typography

interface ToolCardProps {
  title: string
  description: string
  icon: React.ReactNode
  color: string
  status?: { label: string; color: string }
  onClick: () => void
}

function ToolCard({ title, description, icon, color, status, onClick }: ToolCardProps) {
  return (
    <Card hoverable onClick={onClick} styles={{ body: { padding: 20 } }}>
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div style={{
          width: 44, height: 44, borderRadius: 10,
          background: `${color}12`, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          fontSize: 22, color, flexShrink: 0, marginTop: 2,
        }}>
          {icon}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Text strong style={{ fontSize: 14 }}>{title}</Text>
            {status && <Tag color={status.color} style={{ margin: 0, fontSize: 11 }}>{status.label}</Tag>}
          </div>
          <Text type="secondary" style={{ fontSize: 12, lineHeight: '18px' }}>{description}</Text>
          <div style={{ marginTop: 8 }}>
            <Button type="link" size="small" icon={<RightOutlined />} style={{ padding: 0 }}>进入</Button>
          </div>
        </div>
      </div>
    </Card>
  )
}

export default function ToolsPage({ onNavigate }: { currentShop?: string; onNavigate?: (tab: string) => void }) {

  const tools: ToolCardProps[] = [
    {
      title: '定价计算器',
      description: '成本核算、利润计算、Ozon 佣金与物流成本预估',
      icon: <CalculatorOutlined />,
      color: '#1677FF',
      onClick: () => onNavigate?.('pricing'),
    },
    {
      title: 'Listing 生成',
      description: 'AI 生成俄语商品标题、描述和 SEO 关键词',
      icon: <FileTextOutlined />,
      color: '#f59e0b',
      onClick: () => onNavigate?.('listing-generator'),
    },
    {
      title: 'Ozon 知识库',
      description: '平台规则、佣金费率、物流政策、推广工具说明',
      icon: <BookOutlined />,
      color: '#06b6d4',
      onClick: () => onNavigate?.('ozon-rules'),
    },
    {
      title: '自动运营',
      description: '自动化定价、商品上架、库存管理 — 定时任务驱动',
      icon: <RobotOutlined />,
      color: '#8b5cf6',
      onClick: () => onNavigate?.('auto-pilot'),
    },
    {
      title: '工作流引擎',
      description: '选品→图片→Listing→定价→上架全自动化流程',
      icon: <RobotOutlined />,
      color: '#22c55e',
      onClick: () => onNavigate?.('auto-pilot'),
    },
    {
      title: '系统设置',
      description: '店铺配置、API 密钥、通知渠道管理',
      icon: <SettingOutlined />,
      color: '#6b7280',
      onClick: () => onNavigate?.('system'),
    },
  ]

  return (
    <div>
      <PageHeader title="工具" subtitle="定价 / Listing 生成 / 知识库 / 自动运营" />
      <Row gutter={[12, 12]}>
        {tools.map((tool, i) => (
          <Col key={i} xs={24} sm={12} lg={8}>
            <ToolCard {...tool} />
          </Col>
        ))}
      </Row>
    </div>
  )
}
