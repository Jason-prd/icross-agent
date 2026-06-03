import { useState } from 'react'
import { Card, Input, Button, Typography, Space, message, Tabs, Form, Select, Descriptions, Tag, Row, Col } from 'antd'
import { FileTextOutlined, SendOutlined, SaveOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import { useMutation } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

const { TextArea } = Input
const { Text, Title } = Typography

interface ListingResult {
  title: string
  description: string
  keywords: string[]
}

export default function ListingGenerator() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const [productName, setProductName] = useState('')
  const [productDesc, setProductDesc] = useState('')
  const [category, setCategory] = useState('')
  const [keywords, setKeywords] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [result, setResult] = useState<ListingResult | null>(null)

  const generateMutation = useMutation({
    mutationFn: async () => {
      const { data } = await axios.post('/api/listings/generate', {
        shop_id: currentShop,
        product_name_cn: productName,
        product_description_cn: productDesc,
        category: category,
        keyword_str: keywords,
        template_id: templateId || undefined,
      })
      return data
    },
    onSuccess: (data) => {
      if (data.listing) {
        setResult(data.listing)
      } else {
        setResult(data)
      }
      message.success('Listing 生成成功')
    },
    onError: (e: any) => {
      message.error(e.response?.data?.detail || '生成失败')
    },
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!result) return
      await axios.post('/api/listings', {
        shop_id: currentShop,
        product_name_cn: productName,
        title: result.title,
        description: result.description,
        keywords: result.keywords,
        category,
      })
    },
    onSuccess: () => message.success('已保存'),
  })

  return (
    <div>
      <PageHeader title="Listing 生成" subtitle="AI 生成俄语商品标题、描述和关键词" />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="产品信息" size="small">
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>产品中文名称 *</Text>
                <Input
                  placeholder="如：无线蓝牙耳机"
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>产品中文描述</Text>
                <TextArea
                  rows={4}
                  placeholder="描述产品特点、材质、规格等…"
                  value={productDesc}
                  onChange={(e) => setProductDesc(e.target.value)}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>类目</Text>
                <Input
                  placeholder="产品所属类目"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>关键词（逗号分隔）</Text>
                <Input
                  placeholder="蓝牙耳机, 无线耳机, TWS"
                  value={keywords}
                  onChange={(e) => setKeywords(e.target.value)}
                />
              </div>
              <Button
                type="primary"
                icon={<FileTextOutlined />}
                onClick={() => generateMutation.mutate()}
                loading={generateMutation.isPending}
                disabled={!productName.trim()}
                block
                size="large"
              >
                生成 Listing
              </Button>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="生成结果" size="small">
            {result ? (
              <Space direction="vertical" style={{ width: '100%' }} size={12}>
                <div>
                  <Text strong style={{ fontSize: 13 }}>俄语标题</Text>
                  <Card size="small" style={{ marginTop: 4, background: '#fafafa' }}>
                    <Text copyable>{result.title}</Text>
                  </Card>
                </div>
                <div>
                  <Text strong style={{ fontSize: 13 }}>俄语描述</Text>
                  <Card size="small" style={{ marginTop: 4, background: '#fafafa', maxHeight: 300, overflow: 'auto' }}>
                    <Text copyable>{result.description}</Text>
                  </Card>
                </div>
                <div>
                  <Text strong style={{ fontSize: 13 }}>关键词</Text>
                  <div style={{ marginTop: 4 }}>
                    <Space wrap>
                      {result.keywords.map((kw, i) => (
                        <Tag key={i} color="blue">{kw}</Tag>
                      ))}
                    </Space>
                  </div>
                </div>
                <Button icon={<SaveOutlined />} onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
                  保存 Listing
                </Button>
              </Space>
            ) : (
              <div style={{ textAlign: 'center', padding: 60, color: '#bbb' }}>
                <FileTextOutlined style={{ fontSize: 40, opacity: 0.3 }} />
                <div style={{ marginTop: 12 }}>输入产品信息后点击生成</div>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
