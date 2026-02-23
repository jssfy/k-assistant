export interface ToolCallInfo {
  tool: string
  arguments: Record<string, unknown>
  result?: string
  status: 'calling' | 'done'
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  model?: string
  token_usage?: number
  created_at: string
  tool_calls?: ToolCallInfo[]
}

export interface Conversation {
  id: string
  title: string | null
  model: string
  created_at: string
  updated_at: string
  messages?: Message[]
}

export interface ChatResponse {
  conversation_id: string
  message: Message
}

export interface ModelInfo {
  id: string
  owned_by: string
}

export interface MemoryItem {
  id: string
  memory: string
  metadata: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
}
