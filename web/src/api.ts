import type { ChatResponse, Conversation, ModelInfo } from './types'

const API_BASE = '/api'

export async function sendMessage(
  message: string,
  conversationId?: string,
  model?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      model,
    }),
  })
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`)
  return res.json()
}

export async function streamMessage(
  message: string,
  conversationId?: string,
  model?: string,
  onDelta: (content: string) => void = () => {},
  onMetadata: (data: { conversation_id: string; model: string }) => void = () => {},
  onDone: (data: { message_id: string }) => void = () => {},
  onError: (error: string) => void = () => {},
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      model,
    }),
  })
  if (!res.ok) throw new Error(`Stream failed: ${res.status}`)

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let eventType = ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7)
      } else if (line.startsWith('data: ') && eventType) {
        const data = JSON.parse(line.slice(6))
        switch (eventType) {
          case 'message':
            onDelta(data.content)
            break
          case 'metadata':
            onMetadata(data)
            break
          case 'done':
            onDone(data)
            break
          case 'error':
            onError(data.message)
            break
        }
        eventType = ''
      }
    }
  }
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/conversations`)
  if (!res.ok) throw new Error(`Failed to list conversations: ${res.status}`)
  return res.json()
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`${API_BASE}/conversations/${id}`)
  if (!res.ok) throw new Error(`Failed to get conversation: ${res.status}`)
  return res.json()
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Failed to delete conversation: ${res.status}`)
}

export async function listModels(): Promise<ModelInfo[]> {
  const res = await fetch(`${API_BASE}/models`)
  if (!res.ok) throw new Error(`Failed to list models: ${res.status}`)
  const data = await res.json()
  return data.models
}
