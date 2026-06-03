import React from 'react'
import { Button, Result } from 'antd'

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; onReset?: () => void },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: undefined })
    this.props.onReset?.()
  }

  render() {
    if (this.state.hasError) {
      return (
        <Result
          status="error"
          title="页面出现错误"
          subTitle={this.state.error?.message || '未知错误，请刷新重试'}
          extra={
            <Button type="primary" onClick={this.handleReset}>
              重试
            </Button>
          }
        />
      )
    }

    return this.props.children
  }
}
