export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  model?: string
  token_usage?: number
  created_at: string
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
