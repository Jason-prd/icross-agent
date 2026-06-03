import { useState, useEffect } from 'react'
import { Layout, Select, Badge, Space, Typography } from 'antd'
import {
  MessageOutlined,
  DashboardOutlined,
  SettingOutlined,
  BellOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'

const { Header, Content } = Layout
const { Text } = Typography

const navItems = [
  { key: '/agent', label: 'Agent 对话', icon: <MessageOutlined /> },
  { key: '/operations', label: '运营工作台', icon: <DashboardOutlined /> },
  { key: '/settings', label: '配置管理', icon: <SettingOutlined /> },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [shopList, setShopList] = useState<{ shop_id: string; name: string }[]>([])
  const [currentShop, setCurrentShop] = useState<string>('')

  useEffect(() => {
    axios.get('/api/shops').then(({ data }) => {
      const shops: { shop_id: string; name: string }[] = data.shops || []
      setShopList(shops)
      if (!currentShop && shops.length > 0) {
        setCurrentShop(shops[0].shop_id)
      }
    })
  }, [])

  const shopOptions = shopList.map((s) => ({
    value: s.shop_id,
    label: s.name || s.shop_id,
  }))

  return (
    <Layout style={{ height: '100vh', background: '#f5f5f5' }}>
      <Header
        style={{
          background: '#fff',
          height: 56,
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #f0f0f0',
          boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        {/* Left: Logo + Nav */}
        <Space size={32}>
          <Text strong style={{ fontSize: 18, color: '#1677FF', letterSpacing: -0.5 }}>
            iCross Agent
          </Text>
          <nav style={{ display: 'flex', gap: 4 }}>
            {navItems.map((item) => (
              <div
                key={item.key}
                onClick={() => navigate(item.key)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 16px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 14,
                  color: location.pathname.startsWith(item.key) ? '#1677FF' : '#666',
                  background: location.pathname.startsWith(item.key) ? '#e6f4ff' : 'transparent',
                  transition: 'all 0.15s',
                }}
              >
                {item.icon}
                <span>{item.label}</span>
              </div>
            ))}
          </nav>
        </Space>

        {/* Right: Shop Selector + Notifications */}
        <Space size={16}>
          <Select
            value={currentShop || undefined}
            onChange={setCurrentShop}
            options={shopOptions}
            placeholder="选择店铺…"
            style={{ width: 180 }}
            size="small"
            notFoundContent="暂无店铺，请在配置管理中添加"
          />
          <Badge count={3} size="small">
            <BellOutlined style={{ fontSize: 18, color: '#666', cursor: 'pointer' }} />
          </Badge>
        </Space>
      </Header>

      <Content style={{ height: 'calc(100vh - 56px)', overflow: 'hidden' }}>
        <Outlet context={{ currentShop, setCurrentShop }} />
      </Content>
    </Layout>
  )
}
