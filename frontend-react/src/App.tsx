import { Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/AppLayout'
import AgentPage from './pages/AgentPage'
import OperationsPage from './pages/OperationsPage'
import SettingsPage from './pages/SettingsPage'
export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Navigate to="/agent" replace />} />
        <Route path="/agent" element={<AgentPage />} />
        <Route path="/operations" element={<OperationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
