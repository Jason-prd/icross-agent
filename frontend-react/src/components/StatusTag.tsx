import { Tag, Tooltip } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  MinusCircleOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons'

interface StatusConfig {
  label: string
  color: string
  icon: React.ReactNode
}

const statusMap: Record<string, StatusConfig> = {
  // Product / Draft statuses
  published: { label: '已上架', color: 'green', icon: <CheckCircleOutlined /> },
  draft: { label: '草稿', color: 'default', icon: <MinusCircleOutlined /> },
  pending: { label: '待审核', color: 'orange', icon: <ClockCircleOutlined /> },
  approved: { label: '已通过', color: 'green', icon: <CheckCircleOutlined /> },
  rejected: { label: '已驳回', color: 'red', icon: <CloseCircleOutlined /> },
  archived: { label: '已归档', color: 'default', icon: <MinusCircleOutlined /> },

  // Task statuses
  running: { label: '运行中', color: 'processing', icon: <SyncOutlined /> },
  completed: { label: '已完成', color: 'success', icon: <CheckCircleOutlined /> },
  failed: { label: '失败', color: 'error', icon: <CloseCircleOutlined /> },
  cancelled: { label: '已取消', color: 'default', icon: <MinusCircleOutlined /> },
  success: { label: '成功', color: 'success', icon: <CheckCircleOutlined /> },

  // Order statuses
  awaiting_packaging: { label: '待打包', color: 'orange', icon: <ClockCircleOutlined /> },
  awaiting_delivery: { label: '待配送', color: 'processing', icon: <SyncOutlined /> },
  delivered: { label: '已配送', color: 'green', icon: <CheckCircleOutlined /> },
  order_cancelled: { label: '已取消', color: 'default', icon: <CloseCircleOutlined /> },

  // Shop / API status
  active: { label: '正常', color: 'green', icon: <CheckCircleOutlined /> },
  suspended: { label: '暂停', color: 'orange', icon: <ExclamationCircleOutlined /> },
  expired: { label: '过期', color: 'red', icon: <CloseCircleOutlined /> },

  // Campaign status
  running_campaign: { label: '投放中', color: 'green', icon: <CheckCircleOutlined /> },
  planned: { label: '计划中', color: 'processing', icon: <ClockCircleOutlined /> },
  stopped: { label: '已暂停', color: 'default', icon: <MinusCircleOutlined /> },
  finished: { label: '已结束', color: 'default', icon: <MinusCircleOutlined /> },

  // Connection / online status
  online: { label: '在线', color: 'green', icon: <CheckCircleOutlined /> },
  offline: { label: '离线', color: 'default', icon: <CloseCircleOutlined /> },

  // Generic
  enabled: { label: '已启用', color: 'green', icon: <CheckCircleOutlined /> },
  disabled: { label: '已禁用', color: 'default', icon: <CloseCircleOutlined /> },
}

interface StatusTagProps {
  status: string
  label?: string
  tooltip?: string
  icon?: boolean
}

export default function StatusTag({ status, label, tooltip, icon = true }: StatusTagProps) {
  const config = statusMap[status] || {
    label: label || status,
    color: 'default',
    icon: <QuestionCircleOutlined />,
  }

  const tag = (
    <Tag color={config.color} style={{ margin: 0 }}>
      {icon && <span style={{ marginRight: 4 }}>{config.icon}</span>}
      {label || config.label}
    </Tag>
  )

  if (tooltip) {
    return <Tooltip title={tooltip}>{tag}</Tooltip>
  }

  return tag
}

export { statusMap, type StatusConfig }
