import { Empty, Button, Typography } from 'antd'

const { Text } = Typography

interface EmptyStateProps {
  icon?: React.ReactNode
  title?: string
  description?: string
  actionText?: string
  onAction?: () => void
  actionIcon?: React.ReactNode
  size?: 'small' | 'default' | 'large'
}

export default function EmptyState({
  icon,
  title = '暂无数据',
  description,
  actionText,
  onAction,
  actionIcon,
  size = 'default',
}: EmptyStateProps) {
  const padding = size === 'small' ? '24px 0' : size === 'large' ? '80px 0' : '48px 0'

  return (
    <div style={{ padding, textAlign: 'center' }}>
      <Empty
        image={icon ? undefined : Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <div>
            <Text style={{ fontSize: size === 'small' ? 13 : 14, color: '#999' }}>
              {title}
            </Text>
            {description && (
              <div style={{ marginTop: 4 }}>
                <Text style={{ fontSize: 13, color: '#bbb' }}>{description}</Text>
              </div>
            )}
          </div>
        }
      >
        {actionText && onAction && (
          <Button type="primary" icon={actionIcon} onClick={onAction} size={size === 'small' ? 'small' : 'middle'}>
            {actionText}
          </Button>
        )}
      </Empty>
    </div>
  )
}

export { type EmptyStateProps }
