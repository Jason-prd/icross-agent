import { useState } from 'react'
import { Card, Input, Button, Row, Col, Image, message, Space, Select, Modal, Typography } from 'antd'
import { PictureOutlined, DeleteOutlined, CopyOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import EmptyState from '../../components/EmptyState'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import axios from 'axios'

const { TextArea } = Input
const { Text } = Typography

interface GeneratedImage {
  id: string
  url: string
  prompt: string
  source: string
  created_at: string
}

export default function Images() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()
  const queryClient = useQueryClient()
  const [prompt, setPrompt] = useState('')
  const [size, setSize] = useState('2048x2048')
  const [imageUrl, setImageUrl] = useState('')
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['images', currentShop],
    queryFn: async () => {
      const { data } = await axios.get('/api/images', { params: { shop_id: currentShop, limit: 100 } })
      return data
    },
  })

  const generateMutation = useMutation({
    mutationFn: async () => {
      const { data } = await axios.post('/api/images/generate', { prompt, size, n: 1, shop_id: currentShop })
      return data
    },
    onSuccess: () => {
      message.success('图片生成任务已提交')
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '生成失败'),
  })

  const removeBgMutation = useMutation({
    mutationFn: async () => {
      const { data } = await axios.post('/api/images/remove-bg', { image_url: imageUrl, shop_id: currentShop })
      return data
    },
    onSuccess: () => {
      message.success('背景移除完成')
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '处理失败'),
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.delete(`/api/images/${id}`)
    },
    onSuccess: () => {
      message.success('已删除')
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
  })

  const images: GeneratedImage[] = data?.images || data?.items || []

  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url).then(() => message.success('URL 已复制'))
  }

  return (
    <div>
      <PageHeader title="图片管理" />

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="AI 生成图片" size="small">
            <div style={{ marginBottom: 12 }}>
              <TextArea
                rows={3}
                placeholder="输入图片描述（英文效果更佳）…"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </div>
            <Space>
              <Select value={size} onChange={setSize} style={{ width: 140 }}>
                <Select.Option value="2048x2048">2048x2048</Select.Option>
                <Select.Option value="1024x1024">1024x1024</Select.Option>
                <Select.Option value="1536x1024">1536x1024</Select.Option>
              </Select>
              <Button
                type="primary"
                icon={<PictureOutlined />}
                onClick={() => generateMutation.mutate()}
                loading={generateMutation.isPending}
                disabled={!prompt.trim()}
              >
                生成
              </Button>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="移除背景" size="small">
            <Input
              placeholder="输入图片 URL…"
              value={imageUrl}
              onChange={(e) => setImageUrl(e.target.value)}
              style={{ marginBottom: 12 }}
            />
            <Button
              icon={<PictureOutlined />}
              onClick={() => removeBgMutation.mutate()}
              loading={removeBgMutation.isPending}
              disabled={!imageUrl.trim()}
            >
              移除背景
            </Button>
          </Card>
        </Col>
      </Row>

      <Card title="图片库" size="small" style={{ marginTop: 16 }}>
        {images.length === 0 ? (
          <EmptyState title="暂无图片" description="使用上方工具生成或处理图片" />
        ) : (
          <Image.PreviewGroup>
            <Row gutter={[12, 12]}>
              {images.map((img) => (
                <Col key={img.id} xs={12} sm={8} md={6} lg={4}>
                  <Card
                    size="small"
                    cover={
                      <Image
                        alt={img.prompt}
                        src={img.url}
                        style={{ height: 160, objectFit: 'cover', cursor: 'pointer' }}
                        onClick={() => setPreviewUrl(img.url)}
                        preview={{ visible: false }}
                      />
                    }
                    actions={[
                      <CopyOutlined key="copy" onClick={() => handleCopyUrl(img.url)} />,
                      <DeleteOutlined key="delete" onClick={() => deleteMutation.mutate(img.id)} />,
                    ]}
                  >
                    <Text ellipsis style={{ fontSize: 12, display: 'block' }}>
                      {img.prompt || img.source}
                    </Text>
                  </Card>
                </Col>
              ))}
            </Row>
          </Image.PreviewGroup>
        )}
      </Card>

      <Modal open={!!previewUrl} onCancel={() => setPreviewUrl(null)} footer={null} width={800} centered>
        {previewUrl && <Image src={previewUrl} style={{ width: '100%' }} />}
      </Modal>
    </div>
  )
}
