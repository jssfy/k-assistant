import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteConversation,
  getConversation,
  listConversations,
  streamMessage,
} from './api'
import ChatArea from './components/ChatArea'
import Sidebar from './components/Sidebar'
import type { Conversation, Message, ToolCallInfo } from './types'

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [streamingContent, setStreamingContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [model, setModel] = useState('claude-sonnet')
  const [streamingToolCalls, setStreamingToolCalls] = useState<ToolCallInfo[]>([])
  const toolCallsRef = useRef<ToolCallInfo[]>([])

  const refreshConversations = useCallback(async () => {
    try {
      const convs = await listConversations()
      setConversations(convs)
    } catch (err) {
      console.error('Failed to load conversations', err)
    }
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  const loadConversation = async (id: string) => {
    try {
      const conv = await getConversation(id)
      setActiveConvId(id)
      setMessages(conv.messages || [])
      setModel(conv.model)
    } catch (err) {
      console.error('Failed to load conversation', err)
    }
  }

  const handleNewChat = () => {
    setActiveConvId(null)
    setMessages([])
    setStreamingContent('')
    setStreamingToolCalls([])
    toolCallsRef.current = []
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteConversation(id)
      if (activeConvId === id) handleNewChat()
      refreshConversations()
    } catch (err) {
      console.error('Failed to delete conversation', err)
    }
  }

  const handleSend = async (message: string) => {
    // Optimistically add user message
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: message,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempUserMsg])
    setIsStreaming(true)
    setStreamingContent('')
    setStreamingToolCalls([])
    toolCallsRef.current = []

    try {
      let convId = activeConvId

      await streamMessage(
        message,
        convId || undefined,
        model,
        // onDelta
        (content) => {
          setStreamingContent((prev) => prev + content)
        },
        // onMetadata
        (meta) => {
          convId = meta.conversation_id
          setActiveConvId(meta.conversation_id)
        },
        // onDone
        async () => {
          // Reload conversation to get proper message objects
          if (convId) {
            const conv = await getConversation(convId)
            setMessages(conv.messages || [])
          }
          setStreamingContent('')
          setStreamingToolCalls([])
          toolCallsRef.current = []
          setIsStreaming(false)
          refreshConversations()
        },
        // onError
        (error) => {
          console.error('Stream error:', error)
          setStreamingContent('')
          setStreamingToolCalls([])
          toolCallsRef.current = []
          setIsStreaming(false)
        },
        // onToolCall
        (data) => {
          const newTc: ToolCallInfo = {
            tool: data.tool,
            arguments: data.arguments,
            status: 'calling',
          }
          toolCallsRef.current = [...toolCallsRef.current, newTc]
          setStreamingToolCalls([...toolCallsRef.current])
        },
        // onToolResult
        (data) => {
          toolCallsRef.current = toolCallsRef.current.map((tc) =>
            tc.tool === data.tool && tc.status === 'calling'
              ? { ...tc, result: data.result, status: 'done' as const }
              : tc,
          )
          setStreamingToolCalls([...toolCallsRef.current])
        },
      )
    } catch (err) {
      console.error('Failed to send message', err)
      setStreamingContent('')
      setStreamingToolCalls([])
      toolCallsRef.current = []
      setIsStreaming(false)
    }
  }

  return (
    <div className="flex h-screen bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <Sidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={loadConversation}
        onNew={handleNewChat}
        onDelete={handleDelete}
      />
      <ChatArea
        messages={messages}
        streamingContent={streamingContent}
        streamingToolCalls={streamingToolCalls}
        isStreaming={isStreaming}
        model={model}
        onModelChange={setModel}
        onSend={handleSend}
      />
    </div>
  )
}
