import { useState, useEffect } from 'react'
import { Modal, Steps, Button, Typography, Space, Card, Row, Col, Tag, Result } from 'antd'
import {
  RocketOutlined, KeyOutlined, ShopOutlined, MessageOutlined,
  CheckCircleFilled, GithubOutlined, DockerOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'

const { Text, Title, Paragraph } = Typography

interface SystemStatus {
  demo_mode: boolean
  has_llm: boolean
  has_shops: boolean
  provider_count: number
  shop_count: number
  configured_providers: string[]
}

export default function OnboardingWizard() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState(0)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [dismissed, setDismissed] = useState(() => localStorage.getItem('onboarding_dismissed') === 'true')

  useEffect(() => {
    // Delay check to let the app render first
    const timer = setTimeout(async () => {
      try {
        const { data } = await client.get('/api/system/status')
        setStatus(data)
        // Show wizard if first run and not yet configured
        if (!dismissed && !data.has_llm && !data.has_shops) {
          setOpen(true)
        }
      } catch {
        // Backend not ready yet, skip
      }
    }, 1500)
    return () => clearTimeout(timer)
  }, [dismissed])

  const handleClose = (permanent = false) => {
    setOpen(false)
    if (permanent) {
      setDismissed(true)
      localStorage.setItem('onboarding_dismissed', 'true')
    }
  }

  const handleReset = () => {
    localStorage.removeItem('onboarding_dismissed')
    setDismissed(false)
    setCurrent(0)
    setOpen(true)
  }

  // Expose reset to parent via window for debugging / help menu
  useEffect(() => {
    (window as any).__showOnboarding = handleReset
    return () => { delete (window as any).__showOnboarding }
  }, [])

  if (!status) return null

  const isDemo = status.demo_mode
  const steps = isDemo
    ? [
        { title: '欢迎', icon: <RocketOutlined /> },
        { title: '演示说明', icon: <RocketOutlined /> },
        { title: '下一步', icon: <MessageOutlined /> },
      ]
    : [
        { title: '欢迎', icon: <RocketOutlined /> },
        { title: '配置 AI', icon: <KeyOutlined /> },
        { title: '添加店铺', icon: <ShopOutlined /> },
        { title: '开始使用', icon: <MessageOutlined /> },
      ]

  const stepsContent = isDemo ? [
    // Step 1: Welcome (Demo)
    <div key="demo-welcome" style={{ padding: '16px 0' }}>
      <Result
        icon={<RocketOutlined style={{ color: '#1677FF' }} />}
        title="欢迎使用 iCross Agent"
        subTitle="演示模式下可浏览全部界面，但 AI Agent 和店铺功能不可用"
      />
      <div style={{ marginTop: 16 }}>
        <Title level={5}>✨ 你可以在演示模式中：</Title>
        <ul style={{ lineHeight: 2.4, fontSize: 14, paddingLeft: 20 }}>
          <li>浏览完整的运营工作台界面</li>
          <li>查看看板图表和统计数据</li>
          <li>了解系统功能和操作流程</li>
          <li>预览所有配置管理页面</li>
        </ul>
      </div>
    </div>,

    // Step 2: Deployment options (Demo)
    <div key="demo-setup" style={{ padding: '16px 0' }}>
      <Title level={5}>🚀 部署方式选择</Title>
      <Paragraph type="secondary">选择最适合你的方式，配置 API Key 后即可体验完整功能。</Paragraph>
      <Row gutter={[12, 12]} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card size="small" hoverable onClick={() => window.open('https://github.com/Jason-prd/icross-agent', '_blank')}>
            <Space>
              <GithubOutlined style={{ fontSize: 20, color: '#1677FF' }} />
              <div>
                <Text strong>源码部署</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  需 Python 3.11 + Node.js 18
                </Text>
              </div>
            </Space>
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" hoverable>
            <Space>
              <DockerOutlined style={{ fontSize: 20, color: '#1677FF' }} />
              <div>
                <Text strong>Docker 部署</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  仅需安装 Docker Desktop
                </Text>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
      <div style={{ marginTop: 20, padding: '12px 16px', background: '#fff7e6', borderRadius: 8, border: '1px solid #ffd591' }}>
        <Text strong style={{ color: '#d46b08' }}>⚠️ 需要准备：</Text>
        <div style={{ marginTop: 8, lineHeight: 2 }}>
          <div>1. <b>DeepSeek API Key</b> — 用于 AI 对话（platform.deepseek.com）</div>
          <div>2. <b>Ozon Client ID + API Key</b> — 用于店铺运营（卖家中心 → API）</div>
          <div>3. 编辑 <code>.env</code> 文件填入密钥，设置 <code>ICROSS_DEMO_MODE=false</code> 后重启</div>
        </div>
      </div>
    </div>,

    // Step 3: Start (Demo)
    <div key="demo-start" style={{ padding: '16px 0', textAlign: 'center' }}>
      <Title level={4}>准备好了？</Title>
      <Paragraph type="secondary">
        点击下方按钮开始浏览演示界面，或关闭此向导先配置 API Key。
      </Paragraph>
      <div style={{ marginTop: 24 }}>
        <Button type="primary" size="large" onClick={() => navigate('/operations')} style={{ marginRight: 12 }}>
          查看运营工作台
        </Button>
        <Button size="large" onClick={() => navigate('/settings')}>
          前往配置管理
        </Button>
      </div>
    </div>,
  ] : [
    // ── Normal mode steps ──
    // Step 1: Welcome
    <div key="welcome" style={{ padding: '16px 0' }}>
      <Result
        icon={<RocketOutlined style={{ color: '#1677FF' }} />}
        title="欢迎使用 iCross Agent"
        subTitle="AI 驱动的 Ozon 电商运营系统，三步即可开始使用"
      />
      <div style={{ marginTop: 16, lineHeight: 2 }}>
        <Paragraph>
          iCross Agent 是一个智能助手，帮你完成 <b>选品、Listing 生成、订单管理、财务分析、广告投放</b>等全部运营工作。
        </Paragraph>
        <Paragraph type="secondary">
          接下来几步将引导你完成基本配置。
        </Paragraph>
      </div>
    </div>,

    // Step 2: Configure LLM
    <div key="llm" style={{ padding: '16px 0' }}>
      <Space align="start" size={16}>
        <KeyOutlined style={{ fontSize: 32, color: '#1677FF' }} />
        <div>
          <Title level={5} style={{ marginTop: 0 }}>配置 AI 语言模型</Title>
          <Paragraph type="secondary">
            iCross Agent 需要一个 AI 模型来驱动对话和智能功能。推荐使用 DeepSeek。
          </Paragraph>
        </div>
      </Space>

      <Card size="small" style={{ marginTop: 16, background: '#f6ffed', border: '1px solid #b7eb8f' }}>
        <Space>
          <CheckCircleFilled style={{ color: '#52c41a' }} />
          <Text>DeepSeek 已内置配置，只需填入 API Key</Text>
        </Space>
      </Card>

      <div style={{ marginTop: 16, padding: '12px 16px', background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 8 }}>
        <Text strong>💡 获取 API Key：</Text>
        <div style={{ marginTop: 8, lineHeight: 2 }}>
          1. 访问 <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer">platform.deepseek.com</a> 注册账号<br />
          2. 创建 API Key（费用约 ¥2/百万 tokens）<br />
          3. 在 <code>.env</code> 文件中设置 <code>DEEPSEEK_API_KEY=sk-...</code>
        </div>
      </div>
    </div>,

    // Step 3: Configure Shop
    <div key="shop" style={{ padding: '16px 0' }}>
      <Space align="start" size={16}>
        <ShopOutlined style={{ fontSize: 32, color: '#1677FF' }} />
        <div>
          <Title level={5} style={{ marginTop: 0 }}>添加 Ozon 店铺</Title>
          <Paragraph type="secondary">
            绑定你的 Ozon 店铺后，Agent 才能帮你管理商品、订单和财务。
          </Paragraph>
        </div>
      </Space>

      <div style={{ marginTop: 16, padding: '12px 16px', background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 8 }}>
        <Text strong>📋 准备工作：</Text>
        <div style={{ marginTop: 8, lineHeight: 2 }}>
          1. 登录 <a href="https://seller.ozon.ru" target="_blank" rel="noreferrer">Ozon 卖家中心</a><br />
          2. 进入 设置 → API → 生成密钥对<br />
          3. 复制 Client ID 和 API Key<br />
          4. 在系统设置 → 店铺管理中添加
        </div>
      </div>
    </div>,

    // Step 4: Start using
    <div key="start" style={{ padding: '16px 0', textAlign: 'center' }}>
      <Result
        status="success"
        title="配置完成！"
        subTitle="现在可以开始和 AI Agent 对话了"
      />
      <Paragraph type="secondary">
        试试在 Agent 对话页输入：
      </Paragraph>
      <div style={{
        background: '#f5f5f5', padding: '12px 16px', borderRadius: 8,
        margin: '12px 0', fontStyle: 'italic', color: '#666',
      }}>
        「你好，帮我看看店铺的基本数据」
      </div>
      <div style={{ marginTop: 24 }}>
        <Button type="primary" size="large" onClick={() => { handleClose(true); navigate('/agent') }} style={{ marginRight: 12 }}>
          开始对话
        </Button>
        <Button size="large" onClick={() => { handleClose(true); navigate('/operations') }}>
          查看运营工作台
        </Button>
      </div>
    </div>,
  ]

  return (
    <>
      {/* Floating help button when wizard is dismissed */}
      {dismissed && (
        <div
          onClick={handleReset}
          style={{
            position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
            width: 48, height: 48, borderRadius: 24,
            background: '#1677FF', color: '#fff',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', boxShadow: '0 4px 12px rgba(22,119,255,0.3)',
            fontSize: 20,
          }}
          title="重新显示引导"
        >
          ?
        </div>
      )}

      <Modal
        open={open}
        closable={true}
        onCancel={() => handleClose(false)}
        footer={null}
        width={600}
        destroyOnClose
        maskClosable={false}
      >
        <div style={{ padding: '8px 0' }}>
          {/* Steps indicator */}
          <Steps
            current={current}
            size="small"
            items={steps}
            style={{ marginBottom: 24 }}
          />

          {/* Content */}
          <div style={{ minHeight: 240 }}>
            {stepsContent[current]}
          </div>

          {/* Navigation */}
          <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #f0f0f0', paddingTop: 16 }}>
            <div>
              {current > 0 ? (
                <Button onClick={() => setCurrent(current - 1)}>上一步</Button>
              ) : (
                <Button type="text" onClick={() => handleClose(false)}>稍后再说</Button>
              )}
            </div>
            <Space>
              <Button type="text" onClick={() => handleClose(true)}>
                不再显示
              </Button>
              {current < steps.length - 1 ? (
                <Button type="primary" onClick={() => setCurrent(current + 1)}>
                  下一步
                </Button>
              ) : (
                <Button type="primary" onClick={() => handleClose(true)}>
                  {isDemo ? '开始浏览' : '开始使用'}
                </Button>
              )}
            </Space>
          </div>
        </div>
      </Modal>
    </>
  )
}
