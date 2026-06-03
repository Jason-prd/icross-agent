/** Page wrapper with consistent error boundary + loading layout. */
import { Spin } from 'antd'
import ErrorBoundary from './ErrorBoundary'

interface PageWrapperProps {
  children: React.ReactNode
  loading?: boolean
}

export default function PageWrapper({ children, loading }: PageWrapperProps) {
  return (
    <ErrorBoundary>
      {loading ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}>
          <Spin />
        </div>
      ) : children}
    </ErrorBoundary>
  )
}
