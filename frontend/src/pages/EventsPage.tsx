/** 事件流页：SSE 实时事件 + 审计日志。 */
import { Link, useParams } from 'react-router-dom'
import { useAnimeEvents } from '@/hooks/useAnimeEvents'
import { useStudioStore } from '@/stores/studio'
import { formatTs } from '@/utils/format'

export function EventsPage() {
  const { projectId = '' } = useParams()
  const events = useStudioStore((s) => s.events)
  const clearEvents = useStudioStore((s) => s.clearEvents)
  useAnimeEvents(projectId)

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between">
        <Link to={`/projects/${projectId}`} className="text-sm text-blue-600 hover:underline">
          ← 返回项目
        </Link>
        <button
          className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-100"
          onClick={clearEvents}
        >
          清空
        </button>
      </div>
      <h2 className="mt-2 mb-4 text-xl font-semibold">事件流</h2>
      <ul className="space-y-1.5">
        {events.map((ev, i) => (
          <li key={`${ev.seq}-${i}`} className="rounded border border-gray-200 bg-white px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs text-gray-400">#{ev.seq}</span>
              <span className="font-medium text-blue-700">{ev.type}</span>
              <span className="ml-auto text-xs text-gray-400">{formatTs(ev.ts)}</span>
            </div>
            <pre className="mt-1 overflow-x-auto text-xs text-gray-600">
              {JSON.stringify(ev.payload, null, 2)}
            </pre>
          </li>
        ))}
        {!events.length && (
          <li className="rounded border border-gray-200 bg-white px-4 py-6 text-center text-sm text-gray-400">
            暂无事件，等待 SSE 推送…
          </li>
        )}
      </ul>
    </div>
  )
}
