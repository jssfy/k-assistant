import { useState, useRef, type KeyboardEvent } from 'react'

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 200) + 'px'
    }
  }

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => { setInput(e.target.value); handleInput() }}
          onKeyDown={handleKeyDown}
          placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={disabled || !input.trim()}
          className="rounded-xl bg-blue-600 px-4 py-3 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600"
        >
          Send
        </button>
      </div>
    </div>
  )
}
