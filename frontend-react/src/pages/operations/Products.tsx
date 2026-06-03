import { useState, useEffect, useCallback } from 'react'
import {
  Card, Input, Space, message, Button, Modal, Descriptions, Tag, Image, Tabs,
  Form, InputNumber, Select, Row, Col, Typography, Divider, Collapse, Tooltip, Alert
} from 'antd'
import {
  SearchOutlined, SyncOutlined, EditOutlined, PictureOutlined,
  SaveOutlined, CloseOutlined, EyeOutlined, SendOutlined, WarningFilled,
  RobotOutlined
} from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import StatusTag from '../../components/StatusTag'
import SyncIndicator from '../../components/SyncIndicator'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { useOutletContext } from 'react-router-dom'
import { getCurrencyInfo, formatPrice } from '../../utils/currency'

const { Text, Title } = Typography
const { TextArea } = Input

interface ProductsContext {
  currentShop: string
}

interface Product {
  id: string
  ozon_product_id?: string
  name: string
  offer_id: string
  price: number
  old_price?: number
  stock: number
  status: string | { status?: string; status_name?: string; moderate_status?: string }
  category_name?: string
  description?: string
  images?: string[]
  barcodes?: string[]
  sources?: string[]
  created_at: string
  cost_price?: number
  weight?: number
  height?: number
  width?: number
  length?: number
  currency_code?: string
  push_error?: string | null
  [key: string]: any
}

function getProductStatus(status: string | { status?: string; status_name?: string; moderate_status?: string }): string {
  if (typeof status === 'string') return status
  if (status?.status) return status.status
  if (status?.moderate_status === 'approved') return 'published'
  if (status?.moderate_status === 'in_progress') return 'pending'
  return 'draft'
}

interface EditableAttrOption {
  id: number
  value: string
}

interface EditableAttrDef {
  id: number
  name: string
  type: string
  required: boolean
  is_collection: boolean
  max_value_count: number
  current_values: Array<{ dictionary_value_id?: number; value?: string }>
  options: EditableAttrOption[]
}

function AttributesPanel({ productId, currentShop }: { productId: string; currentShop: string }) {
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['resolved-attributes', productId],
    queryFn: async () => {
      const { data } = await axios.get(`/api/products/${productId}/resolved-attributes`)
      return data.attributes as Array<{ id: number; name: string; values: Array<{ value: string }> }>
    },
    enabled: !!productId,
  })

  // Sync attributes from Ozon when component mounts
  useEffect(() => {
    if (!productId) return
    setSyncing(true)
    setSyncError(null)
    axios.post(`/api/products/${productId}/sync-attributes`)
      .then(() => {
        refetch()
        queryClient.invalidateQueries({ queryKey: ['products'] })
      })
      .catch((e) => {
        setSyncError(e.response?.data?.detail || e.message || '同步失败')
      })
      .finally(() => setSyncing(false))
  }, [productId])

  if (isLoading || syncing) return <div style={{ marginTop: 12, color: '#999' }}>加载中...</div>

  if (syncError) {
    return (
      <div style={{ marginTop: 12 }}>
        <Alert type="warning" message={`属性同步失败: ${syncError}，显示本地数据`} style={{ marginBottom: 12 }} />
        <ReadOnlyAttributes data={data || []} />
      </div>
    )
  }

  return <ReadOnlyAttributes data={data || []} />
}

function ReadOnlyAttributes({ data }: { data: Array<{ id: number; name: string; values: Array<{ value: string }> }> }) {
  // Filter out attribute 4196 (description) and 11254 (rich content)
  // — they're shown separately in the product info and images tabs
  const filtered = data.filter((a) => a.id !== 4196 && a.id !== 11254)

  if (!filtered || filtered.length === 0) {
    return <div style={{ marginTop: 12 }}><Text type="secondary">暂无属性数据</Text></div>
  }

  return (
    <div style={{ marginTop: 12 }}>
      <Descriptions column={1} size="small" bordered>
        {filtered.map((attr, i) => (
          <Descriptions.Item key={i} label={attr.name}>
            {attr.values.map((v) => v.value).join(', ')}
          </Descriptions.Item>
        ))}
      </Descriptions>
    </div>
  )
}

// ── Rich Content helpers ──

function extractRichContentUrls(attributes: any[] | null | undefined): string[] {
  if (!attributes) return []
  const rc = attributes.find((a: any) => a.id === 11254)
  if (!rc) return []
  try {
    const json = JSON.parse(rc.values[0]?.value || '{}')
    return (json.content || []).flatMap((widget: any) =>
      (widget.blocks || []).map((b: any) => b.img?.src).filter(Boolean)
    )
  } catch { return [] }
}

function buildRichContentJson(urls: string[]) {
  return {
    content: [{
      widgetName: "raShowcase",
      type: "roll",
      blocks: urls.map(url => ({
        imgLink: "",
        img: {
          src: url,
          srcMobile: url,
          alt: "",
          position: "width_full",
          positionMobile: "width_full",
        }
      }))
    }]
  }
}

function PushResultDisplay({ calls }: { calls: any[] }) {
  if (!calls.length) return null
  return (
    <div style={{ marginTop: 12, background: '#fafafa', borderRadius: 6, padding: '8px 12px' }}>
      <Text strong style={{ fontSize: 13 }}>推送结果</Text>
      <div style={{ marginTop: 6 }}>
        {calls.map((call, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, fontSize: 13 }}>
            <Tag color={call.status === 'ok' ? 'green' : call.status === 'skipped' ? 'orange' : 'red'} style={{ margin: 0 }}>
              {call.status}
            </Tag>
            <span style={{ color: '#555' }}>{call.api}</span>
            {call.error && <span style={{ color: '#ff4d4f', fontSize: 12 }}>{call.error}</span>}
            {call.reason && <span style={{ color: '#999', fontSize: 12 }}>{call.reason}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Products() {
  const { currentShop } = useOutletContext<ProductsContext>()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState('')
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null)
  const [editing, setEditing] = useState(false)
  const [editForm] = Form.useForm()
  const [lastSyncTime, setLastSyncTime] = useState<string | null>(null)
  const [syncError, setSyncError] = useState<string | null>(null)
  const [genImagePrompt, setGenImagePrompt] = useState('')
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [pushResult, setPushResult] = useState<any[] | null>(null)
  const [editableAttrs, setEditableAttrs] = useState<EditableAttrDef[] | null>(null)
  const [attrsLoading, setAttrsLoading] = useState(false)
  const [imageEditingUrls, setImageEditingUrls] = useState<string[]>([])
  const [savingImages, setSavingImages] = useState(false)
  const [richContentUrls, setRichContentUrls] = useState<string[]>([])
  const [showRawJson, setShowRawJson] = useState(false)
  const [rawJsonValue, setRawJsonValue] = useState('')
  const [savingRichContent, setSavingRichContent] = useState(false)
  const [syncAttrsLoading, setSyncAttrsLoading] = useState(false)
  const [qualityCheckResult, setQualityCheckResult] = useState<any>(null)
  const [showQualityCheck, setShowQualityCheck] = useState(false)
  const [priceSuggestionData, setPriceSuggestionData] = useState<any>(null)
  const [showPriceSuggestion, setShowPriceSuggestion] = useState(false)
  const [showCostInput, setShowCostInput] = useState(false)
  const [costInputForm] = Form.useForm()

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['products', currentShop, page, pageSize],
    queryFn: async () => {
      const { data } = await axios.get('/api/products', {
        params: { shop_id: currentShop, limit: pageSize, offset: (page - 1) * pageSize },
      })
      return data
    },
  })

  const syncMutation = useMutation({
    mutationFn: async () => {
      const { data } = await axios.post('/api/products/sync', null, {
        params: { shop_id: currentShop },
      })
      return data
    },
    onSuccess: () => {
      setLastSyncTime(new Date().toISOString())
      setSyncError(null)
      message.success('同步完成')
      queryClient.invalidateQueries({ queryKey: ['products'] })
      // Background enrich (best-effort; per-product sync works in attributes tab)
      axios.post('/api/products/enrich', null, {
        params: { shop_id: currentShop, language: 'ZH_HANS' },
      }).then((resp) => {
        const n = resp.data?.enriched || 0
        if (n > 0) message.success(`补全 ${n} 个商品描述和属性`)
      }).catch(() => {})
    },
    onError: (e: any) => {
      setSyncError(e.message || '同步失败')
      message.error('同步失败')
    },
  })

  const products: Product[] = data?.items || data?.products || []
  const total = data?.total || data?.total_count || 0

  const handlePriceUpdate = async (productId: string, newPrice: number) => {
    try {
      await axios.patch(`/api/products/${productId}/price`, { new_price: newPrice })
      message.success('价格已更新')
      refetch()
    } catch { message.error('更新失败') }
  }

  const saveProductMutation = useMutation({
    mutationFn: async (values: any) => {
      if (!selectedProduct) return
      await axios.patch(`/api/products/${selectedProduct.id}`, values)
    },
    onSuccess: () => {
      message.success('商品已更新')
      setEditing(false)
      setRichContentUrls([])
      setShowRawJson(false)
      setImageEditingUrls([])
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '更新失败'),
  })

  const pushToOzonMutation = useMutation({
    mutationFn: async (values: any) => {
      if (!selectedProduct) return
      const { data } = await axios.post(`/api/products/${selectedProduct.id}/push`, values)
      return data
    },
    onSuccess: (data: any) => {
      const callStatuses = (data.calls || []).map((c: any) => c.status)
      const allOk = callStatuses.every((s: string) => s === 'ok' || s === 'skipped')
      if (allOk) {
        message.success('商品已推送到 Ozon')
      } else {
        message.warning('部分推送操作未成功，请查看详细信息')
      }
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '推送失败'),
  })

  const genImageMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProduct) return
      const { data } = await axios.post('/api/images/generate', {
        prompt: genImagePrompt || selectedProduct.name,
        size: '1024x1024',
        n: 1,
        shop_id: currentShop,
      })
      return data
    },
    onSuccess: () => {
      message.success('图片生成任务已提交')
      setGenImagePrompt('')
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '生成失败'),
  })

  const aiOptimizeTitleMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProduct) return
      const title = editForm.getFieldValue('name') || selectedProduct.name
      const { data } = await axios.post(`/api/products/${selectedProduct.id}/ai/optimize-title`, {
        title,
        category: selectedProduct.category_name || selectedProduct.category_path || '',
        keywords: [],
      })
      return data
    },
    onSuccess: (data: any) => {
      if (data?.title) {
        editForm.setFieldsValue({ name: data.title })
        const oldVal = data.original_title || selectedProduct?.name || ''
        const truncated = data.title.length > 60 ? data.title.slice(0, 60) + '…' : data.title
        const oldTruncated = oldVal.length > 40 ? oldVal.slice(0, 40) + '…' : oldVal
        message.success({
          content: (
            <div>
              <div>标题已优化</div>
              <div style={{ fontSize: 12, color: '#999', marginTop: 2 }}>
                <span style={{ color: '#999', textDecoration: 'line-through' }}>{oldTruncated}</span>
                {' → '}
                <span style={{ color: '#52c41a' }}>{truncated}</span>
              </div>
            </div>
          ),
          duration: 5,
        })
      } else {
        message.warning('AI 返回异常，请重试')
      }
    },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 优化失败'),
  })

  const aiGenerateDescMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProduct) return
      const { data } = await axios.post(`/api/products/${selectedProduct.id}/ai/generate-description`, {
        name: selectedProduct.name,
        category: selectedProduct.category_name || selectedProduct.category_path || '',
        attributes: selectedProduct.attributes || [],
        description: editForm.getFieldValue('description') || '',
      })
      return data
    },
    onSuccess: (data: any) => {
      if (data?.description) {
        editForm.setFieldsValue({ description: data.description })
        const oldLen = data.original_description?.length || 0
        const newLen = data.description.length
        message.success({
          content: (
            <div>
              <div>描述已生成</div>
              <div style={{ fontSize: 12, color: '#999', marginTop: 2 }}>
                {oldLen > 0 ? `${oldLen}字 → ${newLen}字` : `已生成 ${newLen} 字俄语描述`}
                {data.keywords?.length ? `，含 ${data.keywords.length} 个 SEO 关键词` : ''}
              </div>
            </div>
          ),
          duration: 5,
        })
      } else {
        message.warning('AI 返回异常，请重试')
      }
    },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 生成失败'),
  })

  const aiQualityCheckMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProduct) return
      const { data } = await axios.post(`/api/products/${selectedProduct.id}/ai/quality-check`)
      return data
    },
    onSuccess: (data: any) => {
      setQualityCheckResult(data)
      setShowQualityCheck(true)
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '质量检查失败'),
  })

  const aiCompleteAttrsMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProduct) return
      const { data } = await axios.post(`/api/products/${selectedProduct.id}/ai/complete-attributes`)
      return data
    },
    onSuccess: (data: any) => {
      if (!data?.suggestions?.length) {
        message.info(data?.message || '无建议')
        return
      }
      const formVals: Record<string, any> = {}
      const filledNames: string[] = []
      for (const s of data.suggestions) {
        if (!s.id) continue
        if (s.value == null && s.dictionary_value_id == null) continue
        const attr = editableAttrs?.find((a) => a.id === s.id)
        if (!attr) continue
        const hasOptions = attr.options && attr.options.length > 0
        if (hasOptions && s.dictionary_value_id != null) {
          const opt = attr.options.find((o: any) => o.id === s.dictionary_value_id)
          const displayVal = opt?.value || s.dictionary_value_id
          formVals[`attr_${s.id}`] = attr.is_collection ? [s.dictionary_value_id] : s.dictionary_value_id
          filledNames.push(`${attr.name}: ${displayVal}`)
        } else if (s.value != null) {
          formVals[`attr_${s.id}`] = attr.is_collection ? [s.value] : s.value
          filledNames.push(`${attr.name}: ${s.value}`)
        }
      }
      const keys = Object.keys(formVals)
      if (keys.length > 0) {
        editForm.setFieldsValue(formVals)
        message.success({
          content: (
            <div>
              <div>已填写 {keys.length} 个属性</div>
              <div style={{ fontSize: 12, color: '#999', marginTop: 2 }}>
                {filledNames.slice(0, 5).join('、')}
                {filledNames.length > 5 ? ` …等${filledNames.length}项` : ''}
              </div>
            </div>
          ),
          duration: 5,
        })
      } else {
        message.warning('无可应用的属性建议')
      }
    },
    onError: (e: any) => message.error(e.response?.data?.detail || 'AI 补全失败'),
  })

  const aiSuggestPriceMutation = useMutation({
    mutationFn: async () => {
      if (!selectedProduct) return
      const { data } = await axios.post(`/api/products/${selectedProduct.id}/ai/suggest-price`)
      return data
    },
    onSuccess: (data: any) => {
      // If missing cost data, show input modal
      if (data?.missing_fields?.length) {
        setShowCostInput(true)
        costInputForm.setFieldsValue({
          cost_price: selectedProduct?.cost_price || '',
          weight: selectedProduct?.weight || '',
        })
        return
      }
      if (!data?.suggestions?.length) {
        message.info('无法生成定价建议（缺少数据）')
        return
      }
      setPriceSuggestionData(data)
      setShowPriceSuggestion(true)
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '获取定价建议失败'),
  })

  const submitCostDataMutation = useMutation({
    mutationFn: async (values: { cost_price: number; weight: number }) => {
      if (!selectedProduct) return
      await axios.patch(`/api/products/${selectedProduct.id}`, values)
      setSelectedProduct((prev) => prev ? { ...prev, ...values } : prev)
    },
    onSuccess: () => {
      setShowCostInput(false)
      message.success('成本数据已保存')
      setTimeout(() => aiSuggestPriceMutation.mutate(), 300)
    },
    onError: (e: any) => message.error(e.response?.data?.detail || '保存失败'),
  })

  const openDetail = (product: Product) => {
    setSelectedProduct(product)
    setEditing(false)
    setPushResult(null)
    setEditableAttrs(null)
    setRichContentUrls([])
    setShowRawJson(false)
    setImageEditingUrls([])
    editForm.setFieldsValue({
      name: product.name,
      price: product.price,
      stock: product.stock,
      description: product.description || '',
      cost_price: product.cost_price,
      weight: product.weight,
      width: product.width,
      height: product.height,
      depth: product.depth,
    })
    // Auto-fetch attributes + dimensions from Ozon (lazy per-product)
    setSyncAttrsLoading(true)
    axios.post(`/api/products/${product.id}/sync-attributes`).then(({ data }) => {
      const p = data.product
      if (!p) return
      // Merge updated fields into selected product
      setSelectedProduct((prev) => prev ? { ...prev, ...p } : prev)
      editForm.setFieldsValue({
        weight: p.weight ?? product.weight,
        width: p.width ?? product.width,
        height: p.height ?? product.height,
        depth: p.depth ?? product.depth,
        description: p.description ?? product.description,
      })
    }).catch(() => {}).finally(() => setSyncAttrsLoading(false))
  }

  const enterEditMode = async (product: Product) => {
    setEditing(true)
    setPushResult(null)
    setEditableAttrs(null)
    setImageEditingUrls([...(product.images || [])])
    const initialRcUrls = extractRichContentUrls(product.attributes)
    setRichContentUrls(initialRcUrls.length > 0 ? initialRcUrls : [])
    try {
      const rc = (product.attributes || []).find((a: any) => a.id === 11254)
      setRawJsonValue(rc ? rc.values[0]?.value || '{}' : '{}')
    } catch { setRawJsonValue('{}') }
    setShowRawJson(false)
    editForm.setFieldsValue({
      name: product.name,
      price: product.price,
      stock: product.stock,
      description: product.description || '',
      cost_price: product.cost_price,
      weight: product.weight,
      width: product.width,
      height: product.height,
      depth: product.depth,
    })
    // Load editable attributes for the category
    setAttrsLoading(true)
    try {
      const { data } = await axios.get(`/api/products/${product.id}/editable-attributes`)
      const attrs: EditableAttrDef[] = data.attributes || []
      // Filter out description (4196) and rich content (11254) — shown elsewhere
      const filteredAttrs = attrs.filter((a) => a.id !== 4196 && a.id !== 11254)
      setEditableAttrs(filteredAttrs)
      // Set form values for each attribute
      const formVals: Record<string, any> = {}
      for (const attr of filteredAttrs) {
        const cv = attr.current_values
        const hasOptions = attr.options && attr.options.length > 0
        if (hasOptions && attr.is_collection) {
          formVals[`attr_${attr.id}`] = cv.map((v) => v.dictionary_value_id).filter(v => v != null)
        } else if (hasOptions) {
          formVals[`attr_${attr.id}`] = cv.length > 0 ? cv[0].dictionary_value_id : undefined
        } else if (attr.is_collection) {
          formVals[`attr_${attr.id}`] = cv.map((v) => v.value || v.dictionary_value_id).filter(Boolean)
        } else {
          formVals[`attr_${attr.id}`] = cv.length > 0 ? (cv[0].value ?? cv[0].dictionary_value_id) : undefined
        }
      }
      editForm.setFieldsValue(formVals)
    } catch (e: any) {
      message.warning('无法加载属性定义，属性编辑不可用')
    } finally {
      setAttrsLoading(false)
    }
  }

  const handleEditSave = () => {
    editForm.validateFields().then(values => {
      saveProductMutation.mutate(values)
    })
  }

  const handlePushToOzon = () => {
    editForm.validateFields().then(values => {
      const payload: Record<string, any> = {}

      // Detect changed basic fields
      if (values.name !== selectedProduct?.name) payload.name = values.name
      if (Number(values.price) !== selectedProduct?.price) payload.price = Number(values.price)
      if (Number(values.stock) !== selectedProduct?.stock) payload.stock = Number(values.stock)
      if (values.description !== (selectedProduct?.description || '')) payload.description = values.description
      if (Number(values.weight) !== selectedProduct?.weight) payload.weight = Number(values.weight)
      if (Number(values.width) !== selectedProduct?.width) payload.width = Number(values.width)
      if (Number(values.height) !== selectedProduct?.height) payload.height = Number(values.height)
      if (Number(values.depth) !== selectedProduct?.depth) payload.depth = Number(values.depth)

      // Build attribute values from form
      if (editableAttrs) {
        const attrPayload: Array<{ id: number; values: Array<{ dictionary_value_id?: number; value?: string }> }> = []
        for (const attr of editableAttrs) {
          const formVal = values[`attr_${attr.id}`]
          if (formVal === undefined || formVal === null || formVal === '') continue
          const hasOptions = attr.options && attr.options.length > 0
          if (hasOptions && attr.is_collection) {
            const arr = Array.isArray(formVal) ? formVal : [formVal]
            attrPayload.push({ id: attr.id, values: arr.map((v: any) => ({ dictionary_value_id: Number(v) })) })
          } else if (hasOptions) {
            attrPayload.push({ id: attr.id, values: [{ dictionary_value_id: Number(formVal) }] })
          } else if (attr.is_collection) {
            const arr = Array.isArray(formVal) ? formVal : [formVal]
            attrPayload.push({ id: attr.id, values: arr.map((v: any) => ({ value: String(v) })) })
          } else {
            attrPayload.push({ id: attr.id, values: [{ value: String(formVal) }] })
          }
        }
        if (attrPayload.length > 0) {
          payload.attributes = attrPayload
        }
      }

      if (Object.keys(payload).length === 0) {
        message.info('没有检测到更改')
        return
      }

      pushToOzonMutation.mutate(payload, {
        onSuccess: (data: any) => {
          setPushResult(data?.calls || [])
          setEditing(false)
          setImageEditingUrls([])
        },
      })
    })
  }

  const columns = [
    { key: 'name', title: '商品名称', dataIndex: 'name', width: 250 },
    { key: 'offer_id', title: 'SKU', dataIndex: 'offer_id', width: 120 },
    {
      key: 'price', title: '价格', dataIndex: 'price', width: 110,
      render: (v: number, r: Product) => {
        const { symbol } = getCurrencyInfo(r.currency_code)
        return (
          <span style={{ cursor: 'pointer', color: '#1677FF' }}
            onClick={() => {
              const input = prompt(`输入新价格 (${symbol}):`, String(v))
              if (input) handlePriceUpdate(r.id, Number(input))
            }}
          >
            {formatPrice(v, r.currency_code)}
          </span>
        )
      },
    },
    { key: 'stock', title: '库存', dataIndex: 'stock', width: 80 },
    {
      key: 'status', title: '状态', dataIndex: 'status', width: 100,
      render: (v: string | object) => <StatusTag status={getProductStatus(v)} />,
    },
    { key: 'category_path', title: '类目', dataIndex: 'category_path', width: 220, render: (v: string) => v || '—' },
    {
      key: 'images_count', title: '图片', width: 60,
      render: (_: any, r: Product) => {
        const imgs = r.images || []
        return imgs.length > 0 ? (
          <Image src={imgs[0]} width={32} height={32} style={{ objectFit: 'cover', borderRadius: 4 }}
            preview={{ mask: null }} />
        ) : <Text type="secondary" style={{ fontSize: 11 }}>无</Text>
      },
    },
    {
      key: 'push_error', title: '推送', width: 50,
      render: (_: any, r: Product) => r.push_error ? (
        <Tooltip title={r.push_error}>
          <WarningFilled style={{ color: '#ff4d4f' }} />
        </Tooltip>
      ) : null,
    },
    {
      key: 'actions', title: '操作', width: 120,
      render: (_: any, r: Product) => (
        <Button size="small" type="link" onClick={() => openDetail(r)}>详情</Button>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <PageHeader title="商品管理" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingTop: 8 }}>
          <SyncIndicator
            lastSyncAt={lastSyncTime} syncing={syncMutation.isPending}
            error={syncError} onSync={() => syncMutation.mutate()}
          />
          <Button icon={<SyncOutlined />} onClick={() => syncMutation.mutate()} loading={syncMutation.isPending} size="small">
            同步 Ozon
          </Button>
        </div>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Input
          placeholder="搜索商品…"
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ maxWidth: 320 }} allowClear
        />
      </Card>

      <DataTable
        columns={columns}
        data={products}
        total={total}
        loading={isLoading}
        current={page} pageSize={pageSize}
        onChange={(p, ps) => { setPage(p); setPageSize(ps) }}
        onRefresh={refetch}
        emptyText="暂无商品数据"
      />

      <Modal
        title={
          <Space>
            <span>商品详情</span>
            {selectedProduct?.images?.length ? <Image src={selectedProduct.images[0]} width={32} height={32} style={{ objectFit: 'cover', borderRadius: 4 }} /> : null}
          </Space>
        }
        open={!!selectedProduct}
        onCancel={() => { setSelectedProduct(null); setEditing(false); setPushResult(null); setRichContentUrls([]); setImageEditingUrls([]); setQualityCheckResult(null); setShowQualityCheck(false) }}
        footer={null}
        width={800}
      >
        {selectedProduct && (
          <div style={{ maxHeight: '70vh', overflow: 'auto' }}>
            {/* Action bar */}
            <div style={{ textAlign: 'right', marginBottom: 16 }}>
              {editing ? (
                <Space>
                  <Button type="primary" icon={<SaveOutlined />} onClick={handleEditSave} loading={saveProductMutation.isPending}>
                    保存到本地
                  </Button>
                  <Button icon={<RobotOutlined />} onClick={() => aiQualityCheckMutation.mutate()} loading={aiQualityCheckMutation.isPending}>
                    AI 质量检查
                  </Button>
                  <Button type="primary" ghost icon={<SendOutlined />} onClick={handlePushToOzon} loading={pushToOzonMutation.isPending}>
                    推送到 Ozon
                  </Button>
                  <Button icon={<CloseOutlined />} onClick={() => { setEditing(false); setRichContentUrls([]); setShowRawJson(false); setImageEditingUrls([]) }}>取消</Button>
                </Space>
              ) : (
                <Button icon={<EditOutlined />} onClick={() => enterEditMode(selectedProduct)}>编辑</Button>
              )}
            </div>

            <Tabs items={[
              {
                key: 'info',
                label: '商品信息',
                children: editing ? (
                  /* ── EDIT MODE: Full form, one field per row ── */
                  <Form form={editForm} layout="vertical">
                    <Form.Item name="name" label={<Space size="small">商品名称 <Tooltip title="AI 优化标题（参考 Ozon 规则）"><Button size="small" type="text" icon={<RobotOutlined />} loading={aiOptimizeTitleMutation.isPending} onClick={() => aiOptimizeTitleMutation.mutate()} /></Tooltip></Space>} rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                    <Form.Item name="price" label={<Space size="small">价格 <Tooltip title="AI 定价建议"><Button size="small" type="text" icon={<RobotOutlined />} loading={aiSuggestPriceMutation.isPending} onClick={(e) => { e.stopPropagation(); aiSuggestPriceMutation.mutate() }} /></Tooltip></Space>}>
                      <InputNumber min={0} style={{ width: '100%' }} addonAfter={getCurrencyInfo(selectedProduct.currency_code).symbol} />
                    </Form.Item>
                    <Form.Item name="stock" label="库存">
                      <InputNumber min={0} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="cost_price" label="成本价">
                      <InputNumber min={0} style={{ width: '100%' }} addonAfter={getCurrencyInfo(selectedProduct.currency_code).symbol} />
                    </Form.Item>
                    <Form.Item name="description" label={<Space size="small">描述 <Tooltip title="AI 生成描述（参考 Ozon 规则）"><Button size="small" type="text" icon={<RobotOutlined />} loading={aiGenerateDescMutation.isPending} onClick={() => aiGenerateDescMutation.mutate()} /></Tooltip></Space>}>
                      <TextArea rows={3} />
                    </Form.Item>

                    <Divider style={{ fontSize: 13, color: '#999' }}>物理参数 {syncAttrsLoading && <span style={{ fontSize: 11, color: '#1677ff' }}>同步中…</span>}</Divider>
                    <Form.Item name="weight" label="重量 (g)">
                      <InputNumber min={0} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="width" label="宽 (mm)">
                      <InputNumber min={0} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="height" label="高 (mm)">
                      <InputNumber min={0} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name="depth" label="长 (mm)">
                      <InputNumber min={0} style={{ width: '100%' }} />
                    </Form.Item>

                    {editableAttrs && editableAttrs.length > 0 && (
                      <Collapse size="small" style={{ marginTop: 8 }}
                        items={[{
                          key: 'attrs',
                          label: <Space size="small">属性 ({editableAttrs.length} 项) <Tooltip title="AI 补全属性"><Button size="small" type="text" icon={<RobotOutlined />} loading={aiCompleteAttrsMutation.isPending} onClick={(e) => { e.stopPropagation(); aiCompleteAttrsMutation.mutate() }} /></Tooltip></Space>,
                          children: (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                              {editableAttrs.map((attr) => (
                                <Form.Item key={attr.id} name={`attr_${attr.id}`} label={attr.name} required={attr.required} style={{ marginBottom: 8 }}>
                                  {(attr.options && attr.options.length > 0) ? (
                                    <Select allowClear showSearch
                                      mode={attr.is_collection ? 'multiple' : undefined}
                                      placeholder={`选择${attr.name}`}
                                      options={(attr.options || []).map((o) => ({ label: o.value, value: o.id }))}
                                      style={{ width: '100%' }}
                                    />
                                  ) : attr.is_collection ? (
                                    <Select mode="tags" placeholder={`输入${attr.name}`} style={{ width: '100%' }} />
                                  ) : (
                                    <Input placeholder={`输入${attr.name}`} />
                                  )}
                                </Form.Item>
                              ))}
                            </div>
                          ),
                        }]} />
                    )}
                  </Form>
                ) : (
                  /* ── VIEW MODE: Read-only display ── */
                  <>
                    <Descriptions column={1} size="small" bordered style={{ marginBottom: 16 }}>
                      <Descriptions.Item label="商品名称">{selectedProduct.name}</Descriptions.Item>
                      <Descriptions.Item label="SKU">{selectedProduct.offer_id}</Descriptions.Item>
                      <Descriptions.Item label="Ozon ID">{selectedProduct.ozon_product_id || '—'}</Descriptions.Item>
                      <Descriptions.Item label="类目">{selectedProduct.category_path || selectedProduct.category_name || '—'}</Descriptions.Item>
                      <Descriptions.Item label="状态"><StatusTag status={getProductStatus(selectedProduct.status)} /></Descriptions.Item>
                      <Descriptions.Item label="价格">{formatPrice(selectedProduct.price, selectedProduct.currency_code)}</Descriptions.Item>
                      <Descriptions.Item label="原价">{formatPrice(selectedProduct.old_price, selectedProduct.currency_code)}</Descriptions.Item>
                      <Descriptions.Item label="库存">{selectedProduct.stock}</Descriptions.Item>
                      <Descriptions.Item label="成本价">{formatPrice(selectedProduct.cost_price, selectedProduct.currency_code)}</Descriptions.Item>
                      <Descriptions.Item label="货币">{selectedProduct.currency_code || 'CNY'}</Descriptions.Item>
                      <Descriptions.Item label="描述">
                        {selectedProduct.description || <Text type="secondary">暂无描述</Text>}
                      </Descriptions.Item>
                      <Descriptions.Item label="重量 (g)">{selectedProduct.weight ?? '—'}</Descriptions.Item>
                      <Descriptions.Item label="尺寸 (mm)">
                        {[selectedProduct.width, selectedProduct.depth, selectedProduct.height].every(v => v != null)
                          ? `${selectedProduct.width} × ${selectedProduct.depth} × ${selectedProduct.height}`
                          : '—'}
                      </Descriptions.Item>
                    </Descriptions>

                    {/* View-mode attributes */}
                    <Collapse size="small" style={{ marginTop: 12 }} items={[{
                      key: 'attrs',
                      label: '属性',
                      children: <AttributesPanel productId={selectedProduct.id} currentShop={currentShop} />,
                    }]} />
                  </>
                )
              },
              {
                key: 'images',
                label: '图片',
                children: (
                  <div>
                    {/* Main image */}
                    {(() => {
                      const pi = selectedProduct.primary_image
                      const mainUrl = Array.isArray(pi) ? (pi[0] || '') : (pi || '')
                      return mainUrl ? (
                        <div style={{ marginBottom: 12 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>主图</Text>
                          <Image src={mainUrl} style={{ width: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 6 }} />
                        </div>
                      ) : null
                    })()}

                    {/* Gallery */}
                    {(() => {
                      const images = selectedProduct.images || []
                      const isEditingImages = editing

                      // When not editing, just show the gallery
                      if (!isEditingImages) {
                        return images.length > 0 ? (
                          <>
                            {!selectedProduct.primary_image && <Text type="secondary" style={{ fontSize: 12 }}>图片</Text>}
                            <Image.PreviewGroup>
                              <Row gutter={[8, 8]}>
                                {images.map((url, i) => (
                                  <Col key={i} span={6}>
                                    <Image src={url} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6, cursor: 'pointer' }}
                                      preview={{ mask: <EyeOutlined /> }} />
                                  </Col>
                                ))}
                              </Row>
                            </Image.PreviewGroup>
                          </>
                        ) : (
                          <Text type="secondary">暂无图片</Text>
                        )
                      }

                      // Editing mode: show images with management controls
                      const urls = imageEditingUrls

                      return (
                        <Space direction="vertical" style={{ width: '100%' }}>
                          {urls.length > 0 ? (
                            <Image.PreviewGroup>
                              <Row gutter={[8, 8]}>
                                {urls.map((url, i) => (
                                  <Col key={i} span={6}>
                                    <div style={{ position: 'relative' }}>
                                      <Image src={url} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6 }}
                                        preview={{ mask: <EyeOutlined /> }} />
                                      <Button type="primary" danger size="small"
                                        shape="circle"
                                        icon={<CloseOutlined />}
                                        onClick={() => setImageEditingUrls(urls.filter((_, j) => j !== i))}
                                        style={{ position: 'absolute', top: -8, right: -8, width: 22, height: 22, minWidth: 22 }}
                                      />
                                    </div>
                                  </Col>
                                ))}
                              </Row>
                            </Image.PreviewGroup>
                          ) : (
                            <Text type="secondary">暂无图片</Text>
                          )}

                          <Divider style={{ fontSize: 12, margin: '8px 0' }}>添加图片</Divider>
                          <Input.Search
                            placeholder="粘贴图片 URL 后按回车添加"
                            enterButton="添加"
                            onSearch={(val) => {
                              if (val.trim()) setImageEditingUrls([...urls, val.trim()])
                            }}
                          />
                          <input type="file" accept="image/*" id="product-image-upload" style={{ display: 'none' }}
                            onChange={async (e) => {
                              const file = e.target.files?.[0]
                              if (!file) return
                              const form = new FormData()
                              form.append('file', file)
                              try {
                                const { data } = await axios.post(`/api/products/${selectedProduct.id}/images/upload`, form)
                                if (data.ozon_url) {
                                  setImageEditingUrls([...urls, data.ozon_url])
                                  message.success('已上传到 Ozon CDN')
                                } else {
                                  setImageEditingUrls([...urls, data.local_url])
                                  message.info('已上传到本地，可稍后通过"保存"推送到 Ozon')
                                }
                              } catch (e: any) {
                                message.error(e.response?.data?.detail || e.message || '上传失败')
                              }
                              e.target.value = ''
                            }}
                          />
                          <Button icon={<PictureOutlined />} onClick={() => document.getElementById('product-image-upload')?.click()}>
                            上传图片文件
                          </Button>

                          <Button type="primary" icon={<SaveOutlined />} loading={savingImages}
                            onClick={async () => {
                              setSavingImages(true)
                              try {
                                await axios.put(`/api/products/${selectedProduct.id}/images`, { images: urls })
                                message.success('图片已保存')
                                queryClient.invalidateQueries({ queryKey: ['products'] })
                              } catch (e: any) {
                                message.error(e.response?.data?.detail || e.message || '保存失败')
                              } finally {
                                setSavingImages(false)
                              }
                            }}>
                            保存图片
                          </Button>
                        </Space>
                      )
                    })()}

                    {/* Rich Content (detail gallery) — same edit pattern as product images */}
                    <Divider>详情图集（富内容）</Divider>
                    {(() => {
                      const rcUrls = extractRichContentUrls(selectedProduct.attributes)

                      // View mode
                      if (!editing) {
                        return (
                          <div>
                            {rcUrls.length > 0 ? (
                              <Image.PreviewGroup>
                                <Row gutter={[8, 8]}>
                                  {rcUrls.map((url, i) => (
                                    <Col key={i} span={6}>
                                      <Image src={url}
                                        style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6, cursor: 'pointer' }}
                                        preview={{ mask: <EyeOutlined /> }}
                                      />
                                    </Col>
                                  ))}
                                </Row>
                              </Image.PreviewGroup>
                            ) : (
                              <Text type="secondary">暂无详情图集</Text>
                            )}
                          </div>
                        )
                      }

                      // Edit mode: same pattern as product images
                      const urls = richContentUrls
                      return (
                        <Space direction="vertical" style={{ width: '100%' }}>
                          {urls.length > 0 ? (
                            <Image.PreviewGroup>
                              <Row gutter={[8, 8]}>
                                {urls.map((url, i) => (
                                  <Col key={i} span={6}>
                                    <div style={{ position: 'relative' }}>
                                      <Image src={url} style={{ width: '100%', height: 140, objectFit: 'cover', borderRadius: 6 }}
                                        preview={{ mask: <EyeOutlined /> }} />
                                      <Button type="primary" danger size="small" shape="circle" icon={<CloseOutlined />}
                                        onClick={() => {
                                          const next = [...urls]
                                          next.splice(i, 1)
                                          setRichContentUrls(next)
                                        }}
                                        style={{ position: 'absolute', top: -8, right: -8, width: 22, height: 22, minWidth: 22 }}
                                      />
                                    </div>
                                  </Col>
                                ))}
                              </Row>
                            </Image.PreviewGroup>
                          ) : (
                            <Text type="secondary">暂无详情图集</Text>
                          )}

                          <Divider style={{ fontSize: 12, margin: '8px 0' }}>添加图片</Divider>
                          <Input.Search
                            placeholder="粘贴图片 URL 后按回车添加"
                            enterButton="添加"
                            onSearch={(val) => {
                              if (val.trim()) setRichContentUrls([...urls, val.trim()])
                            }}
                          />
                          <input type="file" accept="image/*" id="rc-image-upload" style={{ display: 'none' }}
                            onChange={async (e) => {
                              const file = e.target.files?.[0]
                              if (!file) return
                              const form = new FormData()
                              form.append('file', file)
                              try {
                                const { data } = await axios.post(`/api/products/${selectedProduct.id}/images/upload`, form)
                                const url = data.ozon_url || data.local_url
                                setRichContentUrls([...urls, url])
                                message.success('已添加图片')
                              } catch (e: any) {
                                message.error(e.message || '上传失败')
                              }
                              e.target.value = ''
                            }}
                          />
                          <Button icon={<PictureOutlined />} onClick={() => document.getElementById('rc-image-upload')?.click()}>
                            上传图片文件
                          </Button>

                          <Space>
                            <Button type="primary" icon={<SaveOutlined />} loading={savingRichContent}
                              onClick={async () => {
                                setSavingRichContent(true)
                                try {
                                  const payload = buildRichContentJson(urls)
                                  await axios.post(`/api/products/${selectedProduct.id}/rich-content`, { rich_content: payload })
                                  message.success('富内容已保存')
                                  queryClient.invalidateQueries({ queryKey: ['products'] })
                                } catch (e: any) {
                                  message.error(e.response?.data?.detail || e.message || '保存失败')
                                } finally {
                                  setSavingRichContent(false)
                                }
                              }}>
                              保存
                            </Button>
                            <Button size="small" onClick={() => setShowRawJson(!showRawJson)}>
                              高级（JSON）
                            </Button>
                          </Space>

                          {showRawJson && (
                            <TextArea rows={6}
                              value={rawJsonValue}
                              onChange={(e) => setRawJsonValue(e.target.value)}
                              placeholder="富内容 JSON…"
                            />
                          )}
                        </Space>
                      )
                    })()}

                    {/* Generate image */}
                    <Divider>生成新图片</Divider>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <TextArea rows={2}
                        placeholder={`基于「${selectedProduct.name}」生成商品图片（英文提示词效果更佳）…`}
                        value={genImagePrompt}
                        onChange={(e) => setGenImagePrompt(e.target.value)}
                      />
                      <Button type="primary" icon={<PictureOutlined />}
                        onClick={() => genImageMutation.mutate()}
                        loading={genImageMutation.isPending}
                      >
                        生成图片
                      </Button>
                    </Space>
                  </div>
                )
              }
            ]} />

            {pushResult && <PushResultDisplay calls={pushResult} />}
          </div>
        )}
      </Modal>

      {/* Quality check result modal */}
      <Modal
        title="AI 质量检查结果"
        open={showQualityCheck}
        onCancel={() => setShowQualityCheck(false)}
        footer={<Button onClick={() => setShowQualityCheck(false)}>关闭</Button>}
        width={560}
      >
        {qualityCheckResult && (
          <div>
            <div style={{ textAlign: 'center', marginBottom: 20 }}>
              <div style={{ fontSize: 48, fontWeight: 700, color: qualityCheckResult.score >= 80 ? '#52c41a' : qualityCheckResult.score >= 60 ? '#faad14' : '#ff4d4f' }}>
                {qualityCheckResult.score}
              </div>
              <Text type="secondary" style={{ fontSize: 13 }}>分</Text>
            </div>

            <div style={{ marginBottom: 16, padding: '8px 12px', background: '#f5f5f5', borderRadius: 6 }}>
              <Text>{qualityCheckResult.summary}</Text>
            </div>

            <Divider style={{ margin: '8px 0', fontSize: 13, color: '#999' }}>检查项</Divider>
            {(qualityCheckResult.items || []).map((item: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
                <Tag color={item.status === 'ok' ? 'green' : item.status === 'warn' ? 'orange' : 'red'} style={{ margin: 0, flexShrink: 0 }}>
                  {item.status === 'ok' ? '通过' : item.status === 'warn' ? '警告' : '错误'}
                </Tag>
                <Text style={{ fontSize: 13 }}>{item.message}</Text>
              </div>
            ))}
          </div>
        )}
      </Modal>

      {/* AI pricing suggestion modal */}
      <Modal
        title="AI 定价建议"
        open={showPriceSuggestion}
        onCancel={() => setShowPriceSuggestion(false)}
        width={560}
        footer={
          priceSuggestionData ? (
            <Space>
              <Button onClick={() => setShowPriceSuggestion(false)}>取消</Button>
              {(() => {
                const reco = priceSuggestionData.suggestions?.find(
                  (s: any) => s.tier === priceSuggestionData.recommended_tier
                )
                if (!reco?.price_cny) return null
                return (
                  <Button type="primary" onClick={() => {
                    editForm.setFieldsValue({ price: reco.price_cny })
                    setShowPriceSuggestion(false)
                    message.success(`已应用 ${reco.tier}: ${reco.price_cny} ${priceSuggestionData.currency}`)
                  }}>
                    应用{priceSuggestionData.recommended_tier}
                  </Button>
                )
              })()}
            </Space>
          ) : null
        }
      >
        {priceSuggestionData && (
          <div>
            {priceSuggestionData.current_analysis && (
              <div style={{ padding: '8px 12px', background: '#f0f5ff', borderRadius: 6, marginBottom: 16, border: '1px solid #d6e4ff' }}>
                <Space>
                  <Text style={{ color: '#1677ff' }}>
                    当前定价：{priceSuggestionData.current_price} {priceSuggestionData.product_currency}
                  </Text>
                </Space>
                {priceSuggestionData.current_analysis && <div style={{ marginTop: 4, color: '#666', fontSize: 13 }}>{priceSuggestionData.current_analysis}</div>}
              </div>
            )}

            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              {(priceSuggestionData.suggestions || []).map((s: any, i: number) => {
                const isRecommended = s.tier === priceSuggestionData.recommended_tier
                return (
                  <Card
                    key={i}
                    size="small"
                    hoverable
                    style={{
                      cursor: 'pointer',
                      borderColor: isRecommended ? '#1677ff' : undefined,
                      background: isRecommended ? '#f0f5ff' : undefined,
                    }}
                    onClick={() => {
                      editForm.setFieldsValue({ price: s.price_cny })
                      setShowPriceSuggestion(false)
                      message.success(`已应用 ${s.tier}: ${s.price_cny} ${priceSuggestionData.currency}`)
                    }}
                  >
                    <Row align="middle" justify="space-between">
                      <Col>
                        <Space>
                          <Text strong style={{ fontSize: 15 }}>{s.tier}</Text>
                          {isRecommended && <Tag color="blue">推荐</Tag>}
                        </Space>
                        <div style={{ marginTop: 4, color: '#666', fontSize: 13 }}>{s.reason}</div>
                      </Col>
                      <Col style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 18, fontWeight: 700, color: '#1677ff' }}>
                          ¥{s.price_cny?.toLocaleString()} <span style={{ fontSize: 12, fontWeight: 400 }}>CNY</span>
                        </div>
                        <div style={{ fontSize: 12, color: '#666' }}>
                          毛利率 {s.margin_pct}% · 利润 ¥{s.profit_cny?.toLocaleString()}
                        </div>
                      </Col>
                    </Row>
                  </Card>
                )
              })}
            </Space>

            {priceSuggestionData.market_note && (
              <Alert
                style={{ marginTop: 16 }}
                type="info"
                showIcon
                message="市场参考"
                description={priceSuggestionData.market_note}
              />
            )}
          </div>
        )}
      </Modal>

      {/* Cost data input modal */}
      <Modal
        title="缺少成本数据"
        open={showCostInput}
        onCancel={() => setShowCostInput(false)}
        onOk={() => {
          costInputForm.validateFields().then((values) => {
            submitCostDataMutation.mutate({
              cost_price: Number(values.cost_price),
              weight: Number(values.weight),
            })
          })
        }}
        confirmLoading={submitCostDataMutation.isPending}
        okText="保存并重新计算"
        width={480}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="生成定价建议需要成本和重量数据"
          description="请输入以下信息后系统将自动计算 Ozon 售价和利润分析。"
        />
        <Form form={costInputForm} layout="vertical">
          <Form.Item name="cost_price" label="成本价 (CNY)" rules={[{ required: true, message: '请输入成本价' }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} addonAfter="¥" />
          </Form.Item>
          <Form.Item name="weight" label="重量" rules={[{ required: true, message: '请输入重量' }]}>
            <InputNumber min={0} precision={1} style={{ width: '100%' }} addonAfter="g" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
