import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, Alert } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import AgentPage from './pages/AgentPage'
import OperationsPage from './pages/OperationsPage'
import SettingsPage from './pages/SettingsPage'
import OnboardingWizard from './components/OnboardingWizard'
import client from './api/client'

function DemoBanner() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    client.get('/api/system/status').then(({ data }) => {
      if (data.demo_mode) setVisible(true)
    }).catch(() => {})
  }, [])
  if (!visible) return null
  return (
    <Alert
      banner
      type="warning"
      message={
        <span>
          <b>演示模式</b> — 数据为模拟数据，AI Agent 不可用。
          配置 API Key 后设置 <code>ICROSS_DEMO_MODE=false</code> 重启以体验完整功能。
        </span>
      }
      closable
      onClose={() => setVisible(false)}
      style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 999 }}
    />
  )
}

export default function App() {
  return (
    <>
      <DemoBanner />
      <OnboardingWizard />
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/agent" replace />} />
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/operations" element={<OperationsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </>
  )
}
