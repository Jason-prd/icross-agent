import { useState } from 'react'
import { Card, Input, Button, Typography, Tag, Space, List, Spin, Empty, Segmented } from 'antd'
import { SearchOutlined, BookOutlined, FileTextOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const { Text, Paragraph } = Typography

interface RuleDoc {
  id: string
  title: string
  content: string
  category: string
  category_name?: string
  summary?: string
}

export default function OzonRules() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['ozon-rules-search', searchQuery, category],
    queryFn: async () => {
      const params: any = { query: searchQuery, limit: 20 }
      if (category) params.category = category
      const { data } = await axios.get('/api/ozon-rules/search', { params })
      return data
    },
    enabled: !!searchQuery,
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['ozon-rules-categories'],
    queryFn: async () => {
      const { data } = await axios.get('/api/ozon-rules/categories')
      return data
    },
  })

  const results: RuleDoc[] = data?.results || []
  const categories: { id: string; name: string; count: number }[] = categoriesData?.categories || []

  const handleSearch = () => {
    if (query.trim()) {
      setSearchQuery(query.trim())
    }
  }

  return (
    <div>
      <PageHeader title="Ozon 知识库" subtitle="平台规则、佣金费率、物流政策、推广工具" />

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space.Compact style={{ width: '100%', maxWidth: 600 }}>
          <Input
            placeholder="搜索规则关键词（如：佣金、图片要求、退货流程）…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={handleSearch}
            prefix={<SearchOutlined />}
            size="large"
          />
          <Button type="primary" onClick={handleSearch} loading={isLoading} size="large">
            搜索
          </Button>
        </Space.Compact>

        {categories.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Space size={4} wrap>
              <Tag
                style={{ cursor: 'pointer' }}
                color={category === '' ? 'blue' : 'default'}
                onClick={() => { setCategory(''); if (searchQuery) setSearchQuery(q => q) }}
              >
                全部
              </Tag>
              {categories.map((c: any) => (
                <Tag
                  key={c.id || c.name}
                  style={{ cursor: 'pointer' }}
                  color={category === (c.id || c.name) ? 'blue' : 'default'}
                  onClick={() => setCategory(c.id || c.name)}
                >
                  {c.name} ({c.count})
                </Tag>
              ))}
            </Space>
          </div>
        )}
      </Card>

      {!searchQuery ? (
        <Empty description="输入关键词搜索 Ozon 平台规则" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : isLoading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : results.length === 0 ? (
        <Empty description={`未找到与「${searchQuery}」相关的规则`} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          dataSource={results}
          renderItem={(doc) => (
            <Card size="small" style={{ marginBottom: 8 }} hoverable>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <FileTextOutlined style={{ fontSize: 20, color: '#1677FF', marginTop: 2 }} />
                <div style={{ flex: 1 }}>
                  <Text strong style={{ fontSize: 14 }}>{doc.title}</Text>
                  {doc.category_name && (
                    <Tag style={{ marginLeft: 8 }}>{doc.category_name}</Tag>
                  )}
                  <Paragraph
                    style={{ fontSize: 13, marginTop: 6, marginBottom: 0 }}
                    ellipsis={{ rows: 3 }}
                    type="secondary"
                  >
                    {doc.summary || doc.content?.slice(0, 300)}
                  </Paragraph>
                </div>
              </div>
            </Card>
          )}
        />
      )}
    </div>
  )
}
