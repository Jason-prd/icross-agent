import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ConfigProvider
          locale={zhCN}
          theme={{
            token: {
              colorPrimary: '#1677FF',
              colorSuccess: '#22c55e',
              colorWarning: '#f59e0b',
              colorError: '#ef4444',
              colorInfo: '#1677FF',
              borderRadius: 6,
              borderRadiusLG: 8,
              borderRadiusSM: 4,
              fontFamily: `-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`,
              fontSize: 14,
              controlHeight: 32,
              paddingContentVertical: 16,
              marginXXS: 4,
              marginXS: 8,
              marginSM: 12,
              margin: 16,
              marginLG: 24,
            },
          }}
        >
          <AntApp>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AntApp>
        </ConfigProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
