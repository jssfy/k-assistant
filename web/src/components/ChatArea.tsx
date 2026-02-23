import { useEffect, useRef } from 'react'
import type { Message } from '../types'
import ChatInput from './ChatInput'
import MessageBubble from './MessageBubble'
import ModelSelector from './ModelSelector'

interface Props {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  model: string
  onModelChange: (model: string) => void
  onSend: (message: string) => void
}

export default function ChatArea({
  messages,
  streamingContent,
  isStreaming,
  model,
  onModelChange,
  onSend,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">K-Assistant</h1>
        <ModelSelector value={model} onChange={onModelChange} />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 && !isStreaming && (
            <div className="text-center text-gray-400 mt-20">
              <p className="text-2xl mb-2">👋</p>
              <p>Start a conversation</p>
            </div>
          )}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {isStreaming && streamingContent && (
            <MessageBubble
              message={{
                id: 'streaming',
                role: 'assistant',
                content: streamingContent,
                created_at: new Date().toISOString(),
              }}
            />
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <ChatInput onSend={onSend} disabled={isStreaming} />
    </div>
  )
}
