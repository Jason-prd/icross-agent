import { Table, Pagination, Skeleton, Empty, Tag, Button, Space } from 'antd'
import type { TableRowSelection } from 'antd/es/table/interface'
import { ReloadOutlined } from '@ant-design/icons'
import { useState, useEffect, useCallback } from 'react'

interface Column<T = any> {
  key: string
  title: string
  dataIndex?: string
  render?: (value: any, record: T, index: number) => React.ReactNode
  width?: number | string
  sorter?: boolean | ((a: T, b: T) => number)
  sortable?: boolean
}

interface DataTableProps<T = any> {
  columns: Column<T>[]
  data: T[]
  total: number
  loading?: boolean
  pageSize?: number
  current?: number
  onChange?: (page: number, pageSize: number) => void
  onRefresh?: () => void
  rowKey?: string | ((record: T) => string)
  rowSelection?: TableRowSelection<T>
  emptyText?: string
  emptyAction?: React.ReactNode
  scroll?: { x?: number | string; y?: number | string }
  size?: 'small' | 'middle' | 'large'
  showSizeChanger?: boolean
  pageSizeOptions?: string[]
}

export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
  total,
  loading = false,
  pageSize: defaultPageSize = 20,
  current: defaultCurrent = 1,
  onChange,
  onRefresh,
  rowKey = 'id',
  rowSelection,
  emptyText = '暂无数据',
  emptyAction,
  scroll = { x: 'max-content' },
  size = 'middle',
  showSizeChanger = true,
  pageSizeOptions = ['10', '20', '50', '100'],
}: DataTableProps<T>) {
  const [current, setCurrent] = useState(defaultCurrent)
  const [pageSize, setPageSize] = useState(defaultPageSize)

  useEffect(() => {
    setCurrent(defaultCurrent)
  }, [defaultCurrent])

  useEffect(() => {
    setPageSize(defaultPageSize)
  }, [defaultPageSize])

  const handleChange = useCallback(
    (page: number, size: number) => {
      setCurrent(page)
      setPageSize(size)
      onChange?.(page, size)
    },
    [onChange],
  )

  // Skeleton rows while loading
  if (loading && data.length === 0) {
    return (
      <div style={{ padding: '8px 0' }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} style={{ display: 'flex', gap: 12, padding: '11px 8px', borderBottom: '1px solid #f0f0f0', alignItems: 'center' }}>
            {columns.map((col) => {
              const width = typeof col.width === 'number' ? Math.min(Math.max(col.width * 0.6, 40), col.width * 0.9) : 80
              return (
                <div key={col.key} style={{ width, flexShrink: 0 }}>
                  <Skeleton.Input active size="small" block style={{ height: 20, borderRadius: 4 }} />
                </div>
              )
            })}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey={rowKey}
        loading={loading}
        size={size}
        scroll={scroll}
        pagination={false}
        rowSelection={rowSelection}
        locale={{
          emptyText: (
            <Empty description={emptyText} style={{ padding: '40px 0' }}>
              {emptyAction}
            </Empty>
          ),
        }}
        style={{ minHeight: 200 }}
      />
      {total > 0 && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 0' }}>
          <Space>
            {onRefresh && (
              <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
                刷新
              </Button>
            )}
            <span style={{ fontSize: 13, color: '#999' }}>共 {total} 条</span>
          </Space>
          <Pagination
            current={current}
            pageSize={pageSize}
            total={total}
            onChange={handleChange}
            showSizeChanger={showSizeChanger}
            pageSizeOptions={pageSizeOptions}
            size="small"
            showTotal={undefined}
          />
        </div>
      )}
    </div>
  )
}

export { type Column, type DataTableProps }
