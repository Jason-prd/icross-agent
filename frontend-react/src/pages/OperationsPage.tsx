import { useState, useEffect } from 'react'
import { Layout, Menu, Typography, Badge, Tag } from 'antd'
import {
  ShoppingOutlined,
  OrderedListOutlined,
  DollarOutlined,
  ToolOutlined,
  BarChartOutlined,
  CustomerServiceOutlined,
} from '@ant-design/icons'
import { useOutletContext } from 'react-router-dom'
import Dashboard from './operations/Dashboard'
import Hub from './operations/Hub'
import Products from './operations/Products'
import Drafts from './operations/Drafts'
import Orders from './operations/Orders'
import Finance from './operations/Finance'
import Pricing from './operations/Pricing'
import Images from './operations/Images'
import Marketing from './operations/Marketing'
import ToolsPage from './operations/ToolsPage'
import AutoPilot from './operations/AutoPilot'
import Service from './operations/Service'
import OperationsData from './operations/OperationsData'
import Reports from './operations/Reports'
import System from './operations/System'
import ListingGenerator from './operations/ListingGenerator'
import OzonRules from './operations/OzonRules'
import FloatingAgent from '../components/FloatingAgent'
import axios from 'axios'

const { Content, Sider } = Layout
const { Text } = Typography

type TabKey =
  | 'dashboard' | 'hub' | 'products' | 'drafts'
  | 'orders' | 'returns' | 'finance' | 'marketing'
  | 'images' | 'pricing' | 'auto-pilot' | 'service'
  | 'operations-data' | 'reports' | 'system' | 'tools'
  | 'listing-generator' | 'ozon-rules'

interface NavItem {
  key: TabKey
  label: string
  icon: React.ReactNode
  badgeKey?: 'products' | 'orders' | 'customers'
}

interface BadgeCounts {
  products: number
  orders: number
  customers: number
}

// Primary navigation (6 items) — seller workflow oriented
const primaryNav: NavItem[] = [
  { key: 'dashboard', label: '工作台', icon: <BarChartOutlined /> },
  { key: 'products', label: '商品', icon: <ShoppingOutlined />, badgeKey: 'products' },
  { key: 'orders', label: '订单', icon: <OrderedListOutlined />, badgeKey: 'orders' },
  { key: 'service', label: '客户', icon: <CustomerServiceOutlined />, badgeKey: 'customers' },
  { key: 'finance', label: '财务', icon: <DollarOutlined /> },
  { key: 'tools', label: '工具', icon: <ToolOutlined /> },
]

// Map primary items to their actual tab key for sub-pages
const SUB_PAGES: Record<string, TabKey[]> = {
  products: ['hub', 'products', 'drafts', 'images'],
  orders: ['orders'],
  service: ['service', 'marketing'],
  finance: ['finance', 'reports', 'operations-data'],
  tools: ['tools', 'pricing', 'listing-generator', 'ozon-rules', 'auto-pilot', 'system'],
}

// Which primary section each tab belongs to
const TAB_SECTION: Record<TabKey, string> = {
  dashboard: 'dashboard',
  hub: 'products', products: 'products', drafts: 'products', images: 'products',
  orders: 'orders', returns: 'orders',
  service: 'service', marketing: 'service',
  finance: 'finance', reports: 'finance', 'operations-data': 'finance',
  pricing: 'tools', 'auto-pilot': 'tools', system: 'tools',
  tools: 'tools', 'listing-generator': 'tools', 'ozon-rules': 'tools',
}

const NAV_LABELS: Record<string, string> = {
  tools: '工具首页',
  hub: '选品上架',
  products: '商品管理',
  drafts: '草稿审核',
  images: '图片管理',
  orders: '订单管理',
  returns: '退货管理',
  service: '客服中心',
  marketing: '营销广告',
  finance: '财务中心',
  reports: '报表中心',
  'operations-data': '运营数据',
  pricing: '定价工具',
  'listing-generator': 'Listing 生成',
  'ozon-rules': 'Ozon 知识库',
  'auto-pilot': '自动运营',
  system: '系统设置',
}

// Features that require Ozon Premier seller status
const PREMIER_FEATURES = new Set(['marketing'])

const NAV_ICONS: Record<string, React.ReactNode> = {
  hub: <ShoppingOutlined />,
  products: <ShoppingOutlined />,
  drafts: <ShoppingOutlined />,
  images: <ShoppingOutlined />,
  orders: <OrderedListOutlined />,
  returns: <OrderedListOutlined />,
  service: <CustomerServiceOutlined />,
  marketing: <CustomerServiceOutlined />,
  finance: <DollarOutlined />,
  reports: <DollarOutlined />,
  'operations-data': <DollarOutlined />,
  pricing: <ToolOutlined />,
  'listing-generator': <ToolOutlined />,
  'ozon-rules': <ToolOutlined />,
  'auto-pilot': <ToolOutlined />,
  system: <ToolOutlined />,
  tools: <ToolOutlined />,
}

function PageContent({ tab, currentShop, onNavigate }: { tab: TabKey; currentShop: string; onNavigate?: (tab: string) => void }) {
  switch (tab) {
    case 'dashboard': return <Dashboard currentShop={currentShop} onNavigate={onNavigate} />
    case 'hub': return <Hub />
    case 'products': return <Products />
    case 'drafts': return <Drafts />
    case 'orders': return <Orders />
    case 'finance': return <Finance />
    case 'pricing': return <Pricing />
    case 'images': return <Images />
    case 'marketing': return <Marketing />
    case 'auto-pilot': return <AutoPilot />
    case 'service': return <Service />
    case 'operations-data': return <OperationsData />
    case 'reports': return <Reports />
    case 'system': return <System />
    case 'tools': return <ToolsPage onNavigate={onNavigate} />
    case 'listing-generator': return <ListingGenerator />
    case 'ozon-rules': return <OzonRules />
    default:
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#bbb', fontSize: 15 }}>
          {tab} — 页面迁移中
        </div>
      )
  }
}

export default function OperationsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard')
  const [showSubNav, setShowSubNav] = useState(false)
  const [badges, setBadges] = useState<BadgeCounts>({ products: 0, orders: 0, customers: 0 })
  const [dismissedBadges, setDismissedBadges] = useState<Record<string, number>>({})
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  // Poll dashboard summary for badge counts
  useEffect(() => {
    if (!currentShop) return
    const fetchBadges = async () => {
      try {
        const { data } = await axios.get('/api/dashboard/summary', {
          params: { shop_id: currentShop },
        })
        setBadges({
          products: data.pending_drafts || 0,
          orders: data.pending_returns || 0,
          customers: data.unread_chats || 0,
        })
      } catch {
        // non-critical
      }
    }
    fetchBadges()
    const timer = setInterval(fetchBadges, 60000)
    return () => clearInterval(timer)
  }, [currentShop])

  const handleNavClick = (item: NavItem) => {
    if (item.key === 'dashboard') {
      setActiveTab('dashboard')
      setShowSubNav(false)
      return
    }

    const section = item.key
    const subPages = SUB_PAGES[section] || []

    // Auto-dismiss badge for this section when user navigates to it
    if (item.badgeKey && badges[item.badgeKey] > 0) {
      const bk = item.badgeKey
      setDismissedBadges(prev => ({
        ...prev,
        [bk]: badges[bk],
      }))
    }

    // If we're already in this section, toggle sub-nav
    if (TAB_SECTION[activeTab] === section && showSubNav) {
      setShowSubNav(false)
      return
    }

    // Show first sub-page or the current tab if it's in this section
    if (subPages.includes(activeTab)) {
      setShowSubNav(true)
    } else {
      setActiveTab(subPages[0] || 'dashboard')
      setShowSubNav(true)
    }
  }

  const section = TAB_SECTION[activeTab] || 'dashboard'
  const subPages = SUB_PAGES[section] || []

  // Build secondary sub-navigation items
  const subNavItems = subPages.map((key) => ({
    key,
    icon: NAV_ICONS[key],
    label: (
      <span>
        {NAV_LABELS[key] || key}
        {PREMIER_FEATURES.has(key) && (
          <Tag color="purple" style={{ marginLeft: 6, fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>Premier</Tag>
        )}
      </span>
    ),
  }))

  // Build primary nav items with badges
  const primaryMenuItems = primaryNav.map((item) => {
    const rawCount = item.badgeKey ? badges[item.badgeKey] : 0
    const dismissed = item.badgeKey ? (dismissedBadges[item.badgeKey] || 0) : 0
    const badgeCount = Math.max(0, rawCount - dismissed)
    const isActive = section === item.key
    return {
      key: item.key,
      icon: item.icon,
      label: (
        <span style={{ fontWeight: isActive ? 500 : 400 }}>
          {item.label}
          {item.badgeKey && badgeCount > 0 && (
            <span style={{
              marginLeft: 8,
              background: '#ff4d4f',
              color: '#fff',
              borderRadius: 10,
              padding: '0 6px',
              fontSize: 11,
              lineHeight: '18px',
              display: 'inline-block',
            }}>
              {badgeCount > 99 ? '99+' : badgeCount}
            </span>
          )}
        </span>
      ),
    }
  })

  return (
    <Layout style={{ height: '100%', background: '#fff' }}>
      <Sider
        width={showSubNav ? 380 : 160}
        style={{
          background: '#fafafa',
          borderRight: '1px solid #f0f0f0',
          overflow: 'auto',
          transition: 'width 0.2s',
        }}
      >
        <div style={{ padding: '16px 16px 8px' }}>
          <Text strong style={{ fontSize: 15 }}>
            运营工作台
          </Text>
        </div>

        {/* Primary navigation */}
        <Menu
          mode="inline"
          selectedKeys={[section]}
          onSelect={({ key }) => {
            const item = primaryNav.find((n) => n.key === key)
            if (item) handleNavClick(item)
          }}
          items={primaryMenuItems}
          style={{
            background: 'transparent',
            borderRight: 'none',
            fontSize: 13,
          }}
        />

        {/* Secondary sub-navigation */}
        {showSubNav && subNavItems.length > 1 && (
          <>
            <div style={{
              margin: '8px 16px 4px',
              height: 1,
              background: '#f0f0f0',
            }} />
            <Menu
              mode="inline"
              selectedKeys={[activeTab]}
              onSelect={({ key }) => {
                setActiveTab(key as TabKey)
              }}
              items={subNavItems}
              style={{
                background: 'transparent',
                borderRight: 'none',
                fontSize: 12,
              }}
            />
          </>
        )}
      </Sider>

      <Content key={activeTab} style={{ padding: 24, overflow: 'auto', background: '#f5f5f5' }} className="page-enter">
        <PageContent tab={activeTab} currentShop={currentShop} onNavigate={(tab) => setActiveTab(tab as TabKey)} />
      </Content>
      <FloatingAgent shopId={currentShop} />
    </Layout>
  )
}
