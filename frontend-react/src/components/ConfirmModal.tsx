import { Modal, Typography, Alert, Space } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'

const { Text } = Typography

type DecisionType = 'human' | 'agent'

interface ConfirmModalProps {
  open: boolean
  title: string
  description: string
  decisionType?: DecisionType
  confirmText?: string
  cancelText?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
  children?: React.ReactNode
}

export default function ConfirmModal({
  open,
  title,
  description,
  decisionType = 'human',
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
  children,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      title={
        <Space>
          <ExclamationCircleOutlined style={{ color: danger ? '#ff4d4f' : '#1677FF' }} />
          <span>{title}</span>
        </Space>
      }
      okText={confirmText}
      cancelText={cancelText}
      okButtonProps={{ danger }}
      onOk={onConfirm}
      onCancel={onCancel}
      centered
    >
      <div style={{ margin: '16px 0' }}>
        <Text>{description}</Text>
      </div>

      {decisionType === 'human' && (
        <Alert
          type="info"
          showIcon
          message="此操作需要你的确认"
          description="Agent 已生成执行方案，请审核后决定是否执行。"
          style={{ marginBottom: 12, fontSize: 13 }}
        />
      )}

      {decisionType === 'agent' && (
        <Alert
          type="warning"
          showIcon
          message="Agent 自动执行"
          description="此操作由 Agent 根据预设规则自动执行，无需人工确认。"
          style={{ marginBottom: 12, fontSize: 13 }}
        />
      )}

      {children}
    </Modal>
  )
}

export { type ConfirmModalProps, type DecisionType }
