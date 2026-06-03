import { Typography, Breadcrumb, Space, Tag, Button } from 'antd'
import { HomeOutlined } from '@ant-design/icons'

const { Title } = Typography

interface BreadcrumbItem {
  label: string
  href?: string
}

interface PageHeaderProps {
  title: string
  subtitle?: string
  breadcrumbs?: BreadcrumbItem[]
  actions?: React.ReactNode
  status?: { label: string; color: string }
}

export default function PageHeader({ title, subtitle, breadcrumbs, actions, status }: PageHeaderProps) {
  return (
    <div style={{ marginBottom: 20 }}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <Breadcrumb
          items={[
            { title: <span><HomeOutlined style={{ marginRight: 4 }} />工作台</span> },
            ...breadcrumbs.map((b) => ({
              title: b.href ? <a href={b.href}>{b.label}</a> : b.label,
            })),
          ]}
          style={{ marginBottom: 8, fontSize: 13 }}
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Space align="center" size={12}>
          <Title level={4} style={{ margin: 0 }}>{title}</Title>
          {subtitle && <span style={{ color: '#999', fontSize: 13 }}>{subtitle}</span>}
          {status && <Tag color={status.color}>{status.label}</Tag>}
        </Space>
        {actions && <Space>{actions}</Space>}
      </div>
    </div>
  )
}

export { type PageHeaderProps }
