/** 生成任务页：可观测 / 取消 / 重试。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { cancelJob, listJobs, retryJob } from '@/api/anime'
import { JobStatusBadge } from '@/components/StatusBadge'
import { formatTs } from '@/utils/format'

export function JobsPage() {
  const { projectId = '' } = useParams()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['jobs', projectId],
    queryFn: () => listJobs(projectId),
    refetchInterval: 2000,
  })

  const cancel = useMutation({
    mutationFn: ({ pid, jid }: { pid: string; jid: string }) => cancelJob(pid, jid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs', projectId] }),
  })
  const retry = useMutation({
    mutationFn: ({ pid, jid }: { pid: string; jid: string }) => retryJob(pid, jid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['jobs', projectId] }),
  })

  if (isLoading) return <div className="text-sm text-gray-500">加载中…</div>

  return (
    <div className="max-w-4xl">
      <Link to={`/projects/${projectId}`} className="text-sm text-blue-600 hover:underline">
        ← 返回项目
      </Link>
      <h2 className="mt-2 mb-4 text-xl font-semibold">生成任务</h2>
      <table className="w-full rounded border border-gray-200 bg-white text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
            <th className="px-3 py-2">任务</th>
            <th className="px-3 py-2">Provider</th>
            <th className="px-3 py-2">状态</th>
            <th className="px-3 py-2">重试</th>
            <th className="px-3 py-2">创建时间</th>
            <th className="px-3 py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          {(data?.jobs ?? []).map((j) => (
            <tr key={j.id} className="border-b border-gray-100">
              <td className="px-3 py-2 font-mono text-xs">{j.id}</td>
              <td className="px-3 py-2">{j.provider}</td>
              <td className="px-3 py-2">
                <JobStatusBadge status={j.status} />
              </td>
              <td className="px-3 py-2">{j.retry_count}/{j.max_retries}</td>
              <td className="px-3 py-2 text-xs text-gray-500">{formatTs(j.created_at)}</td>
              <td className="px-3 py-2">
                {j.status === 'FAILED' && (
                  <button
                    className="mr-2 rounded bg-orange-600 px-2 py-1 text-xs text-white hover:bg-orange-700"
                    onClick={() => retry.mutate({ pid: projectId, jid: j.id })}
                  >
                    重试
                  </button>
                )}
                {!['SUCCEEDED', 'FAILED', 'CANCELLED', 'EXPIRED'].includes(j.status) && (
                  <button
                    className="rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700"
                    onClick={() => cancel.mutate({ pid: projectId, jid: j.id })}
                  >
                    取消
                  </button>
                )}
              </td>
            </tr>
          ))}
          {!data?.jobs?.length && (
            <tr>
              <td colSpan={6} className="px-3 py-6 text-center text-gray-400">
                暂无生成任务
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
