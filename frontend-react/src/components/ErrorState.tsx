import { Alert, Button, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

const { Text } = Typography

interface ErrorStateProps {
  title?: string
  description?: string
  onRetry?: () => void
  fullPage?: boolean
}

export default function ErrorState({
  title = '加载失败',
  description,
  onRetry,
  fullPage = false,
}: ErrorStateProps) {
  const content = (
    <Alert
      type="error"
      showIcon
      message={
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <Text strong>{title}</Text>
            {description && (
              <div>
                <Text type="secondary" style={{ fontSize: 13 }}>{description}</Text>
              </div>
            )}
          </div>
          {onRetry && (
            <Button icon={<ReloadOutlined />} size="small" onClick={onRetry}>
              重试
            </Button>
          )}
        </div>
      }
      style={{ marginBottom: 16 }}
    />
  )

  if (fullPage) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 24 }}>
        <div style={{ maxWidth: 480, width: '100%' }}>{content}</div>
      </div>
    )
  }

  return content
}
