import type { Conversation } from '../types'

export type ViewType = 'chat' | 'tasks'

interface Props {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  view: ViewType
  onViewChange: (view: ViewType) => void
}

export default function Sidebar({ conversations, activeId, onSelect, onNew, onDelete, view, onViewChange }: Props) {
  return (
    <div className="w-64 h-full bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex flex-col">
      <div className="p-3 space-y-2">
        <div className="flex rounded-lg bg-gray-200 dark:bg-gray-800 p-0.5">
          <button
            onClick={() => onViewChange('chat')}
            className={`flex-1 text-xs py-1.5 rounded-md font-medium transition-colors ${
              view === 'chat'
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            Chats
          </button>
          <button
            onClick={() => onViewChange('tasks')}
            className={`flex-1 text-xs py-1.5 rounded-md font-medium transition-colors ${
              view === 'tasks'
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            Tasks
          </button>
        </div>
        {view === 'chat' && (
          <button
            onClick={onNew}
            className="w-full rounded-lg border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            + New Chat
          </button>
        )}
      </div>
      {view === 'chat' && (
        <div className="flex-1 overflow-y-auto">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              className={`group flex items-center justify-between px-3 py-2 mx-2 rounded-lg cursor-pointer text-sm ${
                activeId === conv.id
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                  : 'hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <span className="truncate flex-1">{conv.title || 'New Chat'}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(conv.id)
                }}
                className="hidden group-hover:block text-gray-400 hover:text-red-500 ml-2 text-xs"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
