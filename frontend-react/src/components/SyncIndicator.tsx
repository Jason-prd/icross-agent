import { useState, useEffect } from 'react'
import { Space, Typography, Button } from 'antd'
import { SyncOutlined, CheckCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'

const { Text } = Typography

interface SyncIndicatorProps {
  lastSyncAt?: string | null
  onSync?: () => void
  syncing?: boolean
  error?: string | null
}

type SyncStatus = 'fresh' | 'stale' | 'old' | 'error'

function getSyncStatus(lastSyncAt: string | null | undefined, error: string | null | undefined): SyncStatus {
  if (error) return 'error'
  if (!lastSyncAt) return 'old'
  const minutes = dayjs().diff(dayjs(lastSyncAt), 'minute')
  if (minutes < 60) return 'fresh'
  if (minutes < 240) return 'stale'
  return 'old'
}

const STATUS_CONFIG: Record<SyncStatus, { color: string; label: string; icon: React.ReactNode }> = {
  fresh: {
    color: '#52c41a',
    label: '刚刚同步',
    icon: <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 12 }} />,
  },
  stale: {
    color: '#faad14',
    label: '数据较旧',
    icon: <ExclamationCircleOutlined style={{ color: '#faad14', fontSize: 12 }} />,
  },
  old: {
    color: '#d9d9d9',
    label: '未同步',
    icon: <ExclamationCircleOutlined style={{ color: '#d9d9d9', fontSize: 12 }} />,
  },
  error: {
    color: '#ff4d4f',
    label: '同步失败',
    icon: <ExclamationCircleOutlined style={{ color: '#ff4d4f', fontSize: 12 }} />,
  },
}

export default function SyncIndicator({ lastSyncAt, onSync, syncing, error }: SyncIndicatorProps) {
  const status = getSyncStatus(lastSyncAt, error)
  const config = STATUS_CONFIG[status]

  return (
    <Space size={4}>
      {syncing ? (
        <SyncOutlined spin style={{ color: '#1677ff', fontSize: 12 }} />
      ) : (
        config.icon
      )}
      <Text type="secondary" style={{ fontSize: 11 }}>
        {syncing ? '同步中…' : config.label}
        {lastSyncAt && !syncing && ` ${dayjs(lastSyncAt).format('HH:mm')}`}
      </Text>
      {onSync && (
        <Button
          type="link"
          size="small"
          icon={<SyncOutlined />}
          onClick={onSync}
          loading={syncing}
          style={{ fontSize: 11, padding: '0 4px' }}
        >
          同步
        </Button>
      )}
    </Space>
  )
}
