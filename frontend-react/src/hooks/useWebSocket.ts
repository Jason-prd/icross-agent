import { useCallback } from 'react'
import { useChatStore } from '../stores/chatStore'

export function useWebSocket() {
  const connected = useChatStore((s) => s.connected)
  const isStreaming = useChatStore((s) => s.isStreaming)
  const sendMessage = useChatStore((s) => s.sendMessage)
  const stopStreaming = useChatStore((s) => s.stopStreaming)

  const send = useCallback(
    (text: string, shopId: string) => {
      sendMessage(text, shopId)
    },
    [sendMessage],
  )

  const stop = useCallback(() => {
    stopStreaming()
  }, [stopStreaming])

  return {
    connected,
    isStreaming,
    send,
    stop,
  }
}
