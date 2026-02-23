import { useEffect, useState } from 'react'
import { deleteTask, listTaskExecutions, listTasks, toggleTask } from '../api'
import type { ScheduledTask, TaskExecution } from '../types'

function StatusBadge({ active }: { active: boolean }) {
  return active ? (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">
      active
    </span>
  ) : (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400">
      paused
    </span>
  )
}

function ExecStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    success: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  }
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${styles[status] || styles.failed}`}>
      {status}
    </span>
  )
}

function formatTime(iso: string | null) {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function ExecutionRow({ exec }: { exec: TaskExecution }) {
  const [expanded, setExpanded] = useState(false)
  const content = exec.status === 'failed' ? exec.error : exec.result

  return (
    <div className="border-t border-gray-100 dark:border-gray-700">
      <div
        className="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-gray-500 dark:text-gray-400 w-28 shrink-0">{formatTime(exec.started_at)}</span>
        <ExecStatusBadge status={exec.status} />
        {exec.token_usage != null && (
          <span className="text-xs text-gray-400 dark:text-gray-500">{exec.token_usage} tokens</span>
        )}
        <span className="ml-auto text-xs text-gray-400">{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && content && (
        <pre className="px-4 py-2 text-xs bg-gray-50 dark:bg-gray-800/50 text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
          {content}
        </pre>
      )}
    </div>
  )
}

function TaskCard({ task, onRefresh }: { task: ScheduledTask; onRefresh: () => void }) {
  const [execExpanded, setExecExpanded] = useState(false)
  const [executions, setExecutions] = useState<TaskExecution[]>([])
  const [loading, setLoading] = useState(false)

  const loadExecutions = async () => {
    if (!execExpanded) {
      setExecExpanded(true)
      setLoading(true)
      try {
        const execs = await listTaskExecutions(task.id)
        setExecutions(execs)
      } catch (err) {
        console.error('Failed to load executions', err)
      } finally {
        setLoading(false)
      }
    } else {
      setExecExpanded(false)
    }
  }

  const handleToggle = async () => {
    try {
      await toggleTask(task.id, !task.is_active)
      onRefresh()
    } catch (err) {
      console.error('Failed to toggle task', err)
    }
  }

  const handleDelete = async () => {
    if (!confirm(`Delete task "${task.name}"?`)) return
    try {
      await deleteTask(task.id)
      onRefresh()
    } catch (err) {
      console.error('Failed to delete task', err)
    }
  }

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-sm truncate">{task.name}</h3>
              <StatusBadge active={task.is_active} />
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5">
              <div className="font-mono">{task.cron_expression} ({task.timezone})</div>
              {task.next_run_at && <div>Next: {formatTime(task.next_run_at)}</div>}
              {task.last_run_at && <div>Last: {formatTime(task.last_run_at)}</div>}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleToggle}
              className="px-2 py-1 text-xs rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400"
              title={task.is_active ? 'Pause' : 'Resume'}
            >
              {task.is_active ? '⏸' : '▶'}
            </button>
            <button
              onClick={handleDelete}
              className="px-2 py-1 text-xs rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500"
              title="Delete"
            >
              ✕
            </button>
          </div>
        </div>
      </div>
      <div className="border-t border-gray-100 dark:border-gray-700">
        <button
          onClick={loadExecutions}
          className="w-full px-4 py-2 text-xs text-left text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800/50 flex items-center gap-1"
        >
          <span>{execExpanded ? '▼' : '▶'}</span>
          <span>Executions</span>
        </button>
        {execExpanded && (
          <div>
            {loading ? (
              <div className="px-4 py-3 text-xs text-gray-400">Loading...</div>
            ) : executions.length === 0 ? (
              <div className="px-4 py-3 text-xs text-gray-400">No executions yet</div>
            ) : (
              executions.map((exec) => <ExecutionRow key={exec.id} exec={exec} />)
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function TasksPanel() {
  const [tasks, setTasks] = useState<ScheduledTask[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = async () => {
    try {
      const data = await listTasks()
      setTasks(data)
    } catch (err) {
      console.error('Failed to load tasks', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  return (
    <div className="flex-1 flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h1 className="text-lg font-semibold">Scheduled Tasks</h1>
        <span className="text-xs text-gray-400">{tasks.length} tasks</span>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading tasks...</div>
        ) : tasks.length === 0 ? (
          <div className="text-center text-gray-400 py-12">
            <p className="text-lg mb-1">No scheduled tasks</p>
            <p className="text-sm">Create tasks via chat, e.g. "every morning at 9am, summarize tech news"</p>
          </div>
        ) : (
          <div className="space-y-3 max-w-2xl mx-auto">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} onRefresh={refresh} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
