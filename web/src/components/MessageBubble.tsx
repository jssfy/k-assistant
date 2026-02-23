import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, ToolCallInfo } from '../types'

interface Props {
  message: Message
}

function ToolCallPanel({ toolCall }: { toolCall: ToolCallInfo }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="my-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-750 text-left"
      >
        <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>
          ▶
        </span>
        <span className="font-medium">
          {toolCall.status === 'calling' ? '⏳' : '✅'}
        </span>
        <span className="font-mono text-xs text-blue-600 dark:text-blue-400">
          {toolCall.tool}
        </span>
        <span className="text-gray-500 text-xs">
          ({JSON.stringify(toolCall.arguments).slice(0, 60)}
          {JSON.stringify(toolCall.arguments).length > 60 ? '...' : ''})
        </span>
      </button>
      {expanded && (
        <div className="px-3 py-2 text-xs space-y-2 border-t border-gray-200 dark:border-gray-700">
          <div>
            <span className="font-semibold text-gray-600 dark:text-gray-400">Arguments:</span>
            <pre className="mt-1 bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-x-auto">
              {JSON.stringify(toolCall.arguments, null, 2)}
            </pre>
          </div>
          {toolCall.result && (
            <div>
              <span className="font-semibold text-gray-600 dark:text-gray-400">Result:</span>
              <pre className="mt-1 bg-gray-100 dark:bg-gray-900 p-2 rounded overflow-x-auto whitespace-pre-wrap">
                {toolCall.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100'
        }`}
      >
        {/* Tool calls (shown before content for assistant messages) */}
        {!isUser && message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mb-2">
            {message.tool_calls.map((tc, idx) => (
              <ToolCallPanel key={idx} toolCall={tc} />
            ))}
          </div>
        )}

        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
