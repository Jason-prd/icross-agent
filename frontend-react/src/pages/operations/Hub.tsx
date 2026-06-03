import { useState, useEffect, useCallback } from 'react'
import { Tabs, Input, Upload, Button, Card, Table, message, Typography, Space, Tag, Spin, Select, Modal } from 'antd'
import { UploadOutlined, SendOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import EmptyState from '../../components/EmptyState'
import axios from 'axios'
import { useOutletContext } from 'react-router-dom'

const { TextArea } = Input
const { Text, Title } = Typography

type TabKey = 'input' | 'spu' | 'listing' | 'category' | 'draft'
type SessionStatus = 'input' | 'parsed' | 'listing_generated' | 'category_matched' | 'draft_created'

interface SourcingSession {
  id: string
  shop_id: string
  status: SessionStatus
  materials: { text: string; url: string } | null
  parse_result: any | null
  listing_result: any | null
  category_result: any | null
  draft_id: string | null
  created_at: string
  updated_at: string
}

interface ProductsContext {
  currentShop: string
}

const STATUS_LABELS: Record<SessionStatus, string> = {
  input: '待解析',
  parsed: '已解析',
  listing_generated: 'Listing 已生成',
  category_matched: '类目已匹配',
  draft_created: '草稿已创建',
}

export default function Hub() {
  const { currentShop } = useOutletContext<ProductsContext>()
  const [activeTab, setActiveTab] = useState<TabKey>('input')
  const [textInput, setTextInput] = useState('')
  const [files, setFiles] = useState<{name: string; path: string}[]>([])
  const [parseResult, setParseResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [listingResult, setListingResult] = useState<any>(null)
  const [categoryResult, setCategoryResult] = useState<any>(null)
  const [draftResult, setDraftResult] = useState<any>(null)

  // Session persistence
  const [sessions, setSessions] = useState<SourcingSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [showSessionPicker, setShowSessionPicker] = useState(false)
  const [uploadingFiles, setUploadingFiles] = useState(false)

  // Load existing sessions on mount
  useEffect(() => {
    if (!currentShop) return
    loadSessions()
  }, [currentShop])

  const loadSessions = async () => {
    setSessionsLoading(true)
    try {
      const { data } = await axios.get('/api/sourcing/sessions', {
        params: { shop_id: currentShop },
      })
      const incompleted = (data.sessions || []).filter(
        (s: SourcingSession) => s.status !== 'draft_created',
      )
      setSessions(incompleted)
    } catch {
      // silently fail — session saving is a convenience, not critical
    } finally {
      setSessionsLoading(false)
    }
  }

  // Check for existing session on mount; auto-restore most recent
  useEffect(() => {
    if (!sessionsLoading && sessions.length > 0 && !currentSessionId) {
      const latest = sessions[0]
      restoreSession(latest)
    }
  }, [sessions, sessionsLoading])

  const restoreSession = (session: SourcingSession) => {
    setCurrentSessionId(session.id)
    if (session.materials) {
      setTextInput(session.materials.text || '')

    }
    if (session.parse_result) {
      setParseResult(session.parse_result)
    }
    if (session.listing_result) {
      setListingResult(session.listing_result)
    }
    if (session.category_result) {
      setCategoryResult(session.category_result)
    }

    // Navigate to the right tab based on status
    const tabMap: Record<SessionStatus, TabKey> = {
      input: 'input',
      parsed: 'spu',
      listing_generated: 'listing',
      category_matched: 'category',
      draft_created: 'draft',
    }
    setActiveTab(tabMap[session.status] || 'input')
  }

  const createSession = async (): Promise<string | null> => {
    try {
      const { data } = await axios.post('/api/sourcing/sessions', null, {
        params: { shop_id: currentShop },
      })
      const id: string = data.session.id
      setCurrentSessionId(id)
      loadSessions()
      return id
    } catch {
      return null
    }
  }

  const saveSessionState = useCallback(
    async (updates: Partial<{
      status: SessionStatus
      materials: any
      parse_result: any
      listing_result: any
      category_result: any
      draft_id: string
    }>) => {
      let sid = currentSessionId
      if (!sid) {
        sid = await createSession()
        if (!sid) return
      }
      try {
        await axios.put(`/api/sourcing/sessions/${sid}`, {
          shop_id: currentShop,
          ...updates,
        })
      } catch {
        // non-critical
      }
    },
    [currentSessionId, currentShop],
  )

  const handleNewSession = () => {
    setCurrentSessionId(null)
    setTextInput('')
    setFiles([])
    setParseResult(null)
    setListingResult(null)
    setCategoryResult(null)
    setDraftResult(null)
    setActiveTab('input')
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await axios.delete(`/api/sourcing/sessions/${sessionId}`)
      loadSessions()
      if (currentSessionId === sessionId) {
        handleNewSession()
      }
      message.success('已删除')
    } catch {
      message.error('删除失败')
    }
  }

  // ── File upload (real) ──
  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    setUploadingFiles(true)
    try {
      const { data } = await axios.post('/api/upload', formData)
      setFiles((prev) => [...prev, { name: file.name, path: data.path }])
      message.success(`${file.name} 上传成功`)
    } catch (e: any) {
      message.error(`${file.name} 上传失败: ${e.message}`)
    } finally {
      setUploadingFiles(false)
    }
    return false // prevent default upload behavior
  }

  // ── Parse materials ──
  const handleParse = async () => {
    setLoading(true)
    try {
      const materials: any[] = []
      if (textInput.trim()) materials.push({ type: 'text', content: textInput })
      files.forEach((f) => materials.push({ type: 'file', path: f.path }))

      const { data } = await axios.post('/api/parse/product-materials', { materials })
      if (data.success) {
        setParseResult(data)
        setActiveTab('spu')
        await saveSessionState({
          status: 'parsed',
          materials: { text: textInput, url: '' },
          parse_result: data,
        })
        message.success('解析成功')
      } else {
        message.error(data.error || '解析失败')
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || e.message || '解析失败')
    } finally {
      setLoading(false)
    }
  }

  // ── Generate Listing ──
  const handleGenerateListing = async () => {
    if (!parseResult?.spu?.name) return
    setLoading(true)
    try {
      const { data } = await axios.post('/api/listing/generate', {
        product_name_cn: parseResult.spu.name,
        product_description_cn: parseResult.spu.description,
        category: parseResult.spu.category,
        target_market: '俄罗斯',
        skus: parseResult.skus || [],
      })
      const listing = typeof data === 'string' ? JSON.parse(data) : data
      setListingResult(listing)
      setActiveTab('listing')
      await saveSessionState({
        status: 'listing_generated',
        listing_result: listing,
      })
      message.success('Listing 生成成功')
    } catch (e: any) {
      message.error('生成失败')
    } finally {
      setLoading(false)
    }
  }

  // ── Match Category ──
  const handleMatchCategory = async () => {
    if (!parseResult?.spu?.name) return
    setLoading(true)
    try {
      const { data } = await axios.post('/api/categories/match', {
        product_name_cn: parseResult.spu.name,
        product_description_cn: parseResult.spu.description || '',
        top_n: 5,
      })
      if (data.success) {
        setCategoryResult(data)
        setActiveTab('category')
        await saveSessionState({
          status: 'category_matched',
          category_result: data,
        })
        message.success('类目匹配成功')
      } else {
        message.error(data.error || '类目匹配失败')
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || e.message || '类目匹配失败')
    } finally {
      setLoading(false)
    }
  }

  // ── Create Draft ──
  const handleCreateDraft = async () => {
    if (!listingResult) return
    setLoading(true)
    try {
      const matchedCategory = categoryResult?.category
      const body: any = {
        shop_id: currentShop,
        draft_type: 'listing',
        title: listingResult.title || '',
        description: listingResult.description || '',
        price: parseResult?.spu?.price || 0,
        offer_id: '',
        source_url: '',
        images: [],
      }
      if (matchedCategory?.description_category_id) {
        body.description_category_id = matchedCategory.description_category_id
      }
      if (matchedCategory?.type_id) {
        body.type_id = matchedCategory.type_id
      }

      const { data } = await axios.post('/api/drafts/create', body)
      if (data.success) {
        setDraftResult(data.draft)
        setActiveTab('draft')
        await saveSessionState({
          status: 'draft_created',
          draft_id: data.draft?.id,
        })
        message.success('草稿创建成功，请前往审核')
      } else {
        message.error(data.error || '草稿创建失败')
      }
    } catch (e: any) {
      message.error(e.response?.data?.detail || e.message || '草稿创建失败')
    } finally {
      setLoading(false)
    }
  }

  // ── Regenerate listing ──
  const handleRegenerateListing = () => {
    setListingResult(null)
    setActiveTab('spu')
  }

  // ── SPU table data ──
  const spuData = parseResult?.spu
    ? Object.entries(parseResult.spu)
        .filter(([k]) => k !== 'attributes' && k !== 'images')
        .map(([k, v]) => ({ key: k, field: k, value: String(v || '—') }))
    : []

  // ── Session switcher banner ──
  const SessionBanner = () => {
    if (sessions.length === 0) return null
    return (
      <Card size="small" style={{ marginBottom: 16, background: '#fafafa' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {currentSessionId ? '当前选品:' : '未完成选品:'}
            </Text>
            {currentSessionId && sessions.find((s) => s.id === currentSessionId) ? (
              <Tag color="processing">
                {STATUS_LABELS[sessions.find((s) => s.id === currentSessionId)!.status]}
              </Tag>
            ) : sessions.length > 0 ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {sessions.length} 个未完成
              </Text>
            ) : null}
          </Space>
          <Space>
            {currentSessionId && (
              <Button size="small" onClick={() => setShowSessionPicker(true)}>
                切换
              </Button>
            )}
            <Button size="small" icon={<PlusOutlined />} onClick={handleNewSession}>
              新建
            </Button>
          </Space>
        </Space>
      </Card>
    )
  }

  return (
    <div>
      <PageHeader title="选品上架" subtitle="从材料到草稿的一站式流程" />

      <SessionBanner />

      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as TabKey)}
        items={[
          {
            key: 'input',
            label: '输入材料',
            children: (
              <div style={{ maxWidth: 720 }}>
                <Card title="文本描述" size="small" style={{ marginBottom: 16 }}>
                  <TextArea
                    rows={4}
                    placeholder="输入产品描述、规格参数等信息…"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                  />
                </Card>


                <Card title="文件上传" size="small" style={{ marginBottom: 16 }}>
                  <Upload.Dragger
                    multiple
                    accept=".pdf,.xlsx,.xls,.docx,.doc,.pptx,.png,.jpg,.jpeg"
                    beforeUpload={handleUpload}
                    showUploadList={false}
                    disabled={uploadingFiles}
                  >
                    <p><UploadOutlined style={{ fontSize: 24, color: '#1677FF' }} /></p>
                    <p>点击或拖拽文件到此区域上传</p>
                    <p style={{ fontSize: 12, color: '#999' }}>
                      {uploadingFiles ? '上传中…' : '支持 PDF、Excel、Word、PPT、图片'}
                    </p>
                  </Upload.Dragger>
                  {files.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        已上传: {files.map(f => f.name).join(', ')}
                      </Text>
                    </div>
                  )}
                </Card>

                <Space>
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    onClick={handleParse}
                    loading={loading}
                    disabled={!textInput.trim()}
                  >
                    解析材料
                  </Button>
                </Space>
              </div>
            ),
          },
          {
            key: 'spu',
            label: 'SPU/SKU',
            children: parseResult ? (
              <div>
                <Card title="SPU 信息" size="small" style={{ marginBottom: 16 }}>
                  <Table dataSource={spuData} columns={[
                    { key: 'field', title: '字段', dataIndex: 'field', width: 120 },
                    { key: 'value', title: '内容', dataIndex: 'value' },
                  ]} pagination={false} size="small" />
                  {parseResult.spu?.attributes && Object.keys(parseResult.spu.attributes).length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <Text strong>属性: </Text>
                      <Space wrap>
                        {Object.entries(parseResult.spu.attributes).map(([k, v]) => (
                          <Tag key={k}>{k}: {String(v)}</Tag>
                        ))}
                      </Space>
                    </div>
                  )}
                </Card>

                {parseResult.skus?.length > 0 && (
                  <Card title={`SKU 列表 (${parseResult.skus.length})`} size="small" style={{ marginBottom: 16 }}>
                    <Table
                      dataSource={parseResult.skus.map((sku: any, i: number) => ({ ...sku, _key: i }))}
                      columns={[
                        { key: 'name', title: 'SKU 名称', dataIndex: 'name' },
                        { key: 'attributes', title: '规格属性', dataIndex: 'attributes', render: (v: Record<string, string>) => v && Object.keys(v).length > 0 ? Object.entries(v).map(([k, vv]) => `${k}: ${vv}`).join('; ') : '—' },
                        { key: 'price', title: '价格 (¥)', dataIndex: 'price', render: (v: number) => v || '—' },
                        { key: 'stock', title: '库存', dataIndex: 'stock', render: (v: number) => v ?? '—' },
                      ]}
                      pagination={false}
                      size="small"
                      rowKey="_key"
                    />
                  </Card>
                )}

                <Space>
                  <Button type="primary" onClick={handleGenerateListing} loading={loading}>
                    生成 Listing
                  </Button>
                </Space>
              </div>
            ) : (
              <EmptyState title="请先输入材料" description="在「输入材料」标签页提交产品信息" />
            ),
          },
          {
            key: 'listing',
            label: 'Listing',
            children: listingResult ? (
              <div>
                <Card title="俄语标题" size="small" style={{ marginBottom: 16 }}>
                  <Text>{listingResult.title}</Text>
                </Card>
                <Card title="俄语描述" size="small" style={{ marginBottom: 16 }}>
                  <div style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{listingResult.description}</div>
                </Card>
                {listingResult.keywords?.length > 0 && (
                  <Card title="关键词" size="small" style={{ marginBottom: 16 }}>
                    <Space wrap>
                      {listingResult.keywords.map((kw: string, i: number) => (
                        <Tag key={i}>{kw}</Tag>
                      ))}
                    </Space>
                  </Card>
                )}
                <Space>
                  <Button type="primary" onClick={handleMatchCategory} loading={loading}>
                    匹配类目
                  </Button>
                  <Button onClick={handleRegenerateListing}>重新生成</Button>
                </Space>
              </div>
            ) : (
              <EmptyState title="尚未生成 Listing" description="在 SPU/SKU 页面点击「生成 Listing」" />
            ),
          },
          {
            key: 'category',
            label: '类目匹配',
            children: (
              <div style={{ maxWidth: 720 }}>
                {loading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <Spin />
                    <div style={{ marginTop: 12, color: '#999' }}>正在匹配类目…</div>
                  </div>
                ) : categoryResult ? (
                  <div>
                    {categoryResult.category ? (
                      <Card title="匹配结果" size="small" style={{ marginBottom: 16 }}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <div>
                            <Text strong>类目名称: </Text>
                            <Text>{categoryResult.category.name || categoryResult.category.category_name}</Text>
                          </div>
                          {categoryResult.category.description_category_id && (
                            <div>
                              <Text strong>类目 ID: </Text>
                              <Text>{categoryResult.category.description_category_id}</Text>
                            </div>
                          )}
                          {categoryResult.category.type_id && (
                            <div>
                              <Text strong>类型 ID: </Text>
                              <Text>{categoryResult.category.type_id}</Text>
                            </div>
                          )}
                          {categoryResult.confidence && (
                            <div>
                              <Text strong>匹配置信度: </Text>
                              <Text>{(categoryResult.confidence * 100).toFixed(0)}%</Text>
                            </div>
                          )}
                          {categoryResult.method && (
                            <div>
                              <Text strong>匹配方式: </Text>
                              <Tag>{categoryResult.method === 'vector' ? '向量匹配' : 'LLM 匹配'}</Tag>
                            </div>
                          )}
                        </Space>
                      </Card>
                    ) : (
                      <Card title="备选类目" size="small" style={{ marginBottom: 16 }}>
                        {categoryResult.candidates?.map((c: any, i: number) => (
                          <div key={i} style={{ padding: '4px 0' }}>
                            <Text>
                              {i + 1}. {c.name || c.category_name}
                              {c.description_category_id ? ` (ID: ${c.description_category_id})` : ''}
                            </Text>
                          </div>
                        ))}
                      </Card>
                    )}

                    <Space>
                      <Button type="primary" onClick={handleCreateDraft} loading={loading}>
                        创建草稿
                      </Button>
                      <Button onClick={() => setCategoryResult(null)}>重新匹配</Button>
                    </Space>
                  </div>
                ) : (
                  <EmptyState
                    title="尚未匹配类目"
                    description={listingResult ? '点击下方按钮开始匹配' : '请先生成 Listing'}
                    actionText={listingResult ? '开始匹配' : undefined}
                    onAction={listingResult ? handleMatchCategory : undefined}
                  />
                )}
              </div>
            ),
          },
          {
            key: 'draft',
            label: '创建草稿',
            children: draftResult ? (
              <div>
                <Card title="草稿已创建" size="small" style={{ marginBottom: 16 }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div>
                      <Text strong>草稿 ID: </Text>
                      <Text>{draftResult.id}</Text>
                    </div>
                    <div>
                      <Text strong>标题: </Text>
                      <Text>{draftResult.title}</Text>
                    </div>
                    <div>
                      <Text strong>状态: </Text>
                      <Tag color="processing">{draftResult.status || 'pending'}</Tag>
                    </div>
                  </Space>
                </Card>
                <Space>
                  <Button type="primary" onClick={() => window.location.href = '/operations?tab=drafts'}>
                    前往审核
                  </Button>
                  <Button onClick={handleNewSession}>新建选品</Button>
                </Space>
              </div>
            ) : (
              <EmptyState
                title="尚未创建草稿"
                description={categoryResult ? '在类目匹配页面点击「创建草稿」' : '请先完成类目匹配'}
                actionText={categoryResult ? '创建草稿' : undefined}
                onAction={categoryResult ? handleCreateDraft : undefined}
              />
            ),
          },
        ]}
      />

      {/* Session Picker Modal */}
      <Modal
        title="切换选品会话"
        open={showSessionPicker}
        onCancel={() => setShowSessionPicker(false)}
        footer={null}
        width={480}
      >
        {sessions.length === 0 ? (
          <EmptyState title="无未完成选品" description="所有选品流程已完成" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            {sessions.map((s) => (
              <Card
                key={s.id}
                size="small"
                hoverable
                style={{
                  cursor: 'pointer',
                  borderColor: s.id === currentSessionId ? '#1677ff' : undefined,
                }}
                onClick={() => {
                  restoreSession(s)
                  setShowSessionPicker(false)
                }}
              >
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space direction="vertical" size={2}>
                    <Text style={{ fontSize: 13 }}>
                      {s.materials?.text?.slice(0, 60) || s.materials?.url || '未命名'}
                    </Text>
                    <Tag color="default" style={{ fontSize: 11 }}>
                      {STATUS_LABELS[s.status]}
                    </Tag>
                  </Space>
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDeleteSession(s.id)
                    }}
                  />
                </Space>
              </Card>
            ))}
          </Space>
        )}
      </Modal>
    </div>
  )
}
