import { useEffect, useState } from 'react'
import { listModels } from '../api'
import type { ModelInfo } from '../types'

interface Props {
  value: string
  onChange: (model: string) => void
}

export default function ModelSelector({ value, onChange }: Props) {
  const [models, setModels] = useState<ModelInfo[]>([])

  useEffect(() => {
    listModels().then(setModels).catch(console.error)
  }, [])

  if (models.length === 0) return null

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {models.map((m) => (
        <option key={m.id} value={m.id}>
          {m.id}
        </option>
      ))}
    </select>
  )
}
