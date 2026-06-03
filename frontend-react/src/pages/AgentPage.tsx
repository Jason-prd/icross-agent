import { Layout } from 'antd'
import { useOutletContext } from 'react-router-dom'
import SessionList from '../components/SessionList'
import ChatPanel from '../components/ChatPanel'
import ContextPanel from '../components/ContextPanel'

const { Content, Sider } = Layout

export default function AgentPage() {
  const { currentShop } = useOutletContext<{ currentShop: string }>()

  return (
    <Layout style={{ height: '100%', background: '#fff' }}>
      {/* Left: Session List */}
      <Sider
        width={280}
        style={{
          background: '#fafafa',
          borderRight: '1px solid #f0f0f0',
          overflow: 'auto',
        }}
      >
        <SessionList shopId={currentShop} />
      </Sider>

      {/* Center: Chat Panel */}
      <Content
        style={{
          display: 'flex',
          flexDirection: 'column',
          background: '#fff',
        }}
      >
        <ChatPanel shopId={currentShop} />
      </Content>

      {/* Right: Context Panel */}
      <Sider
        width={300}
        style={{
          background: '#fafafa',
          borderLeft: '1px solid #f0f0f0',
          overflow: 'auto',
        }}
      >
        <ContextPanel shopId={currentShop} />
      </Sider>
    </Layout>
  )
}
