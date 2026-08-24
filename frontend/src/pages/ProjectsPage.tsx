/** 项目列表页：创建 + 选择项目。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { createProject, listProjects } from '@/api/anime'

export function ProjectsPage() {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const { data, isLoading, isError } = useQuery({ queryKey: ['projects'], queryFn: listProjects })

  const create = useMutation({
    mutationFn: () => createProject(name, brief),
    onSuccess: () => {
      setName('')
      setBrief('')
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  if (isLoading) return <div className="text-sm text-gray-500">加载中…</div>
  if (isError) return <div className="text-sm text-red-600">加载失败</div>

  return (
    <div className="max-w-3xl">
      <h2 className="mb-4 text-xl font-semibold">短剧项目</h2>

      <form
        className="mb-6 flex flex-col gap-2 rounded border border-gray-200 bg-white p-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (name.trim()) create.mutate()
        }}
      >
        <input
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          placeholder="项目名称（必填）"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="rounded border border-gray-300 px-3 py-2 text-sm"
          placeholder="一句话简介（可选）"
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
        />
        <button
          type="submit"
          disabled={!name.trim() || create.isPending}
          className="self-start rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {create.isPending ? '创建中…' : '创建项目'}
        </button>
      </form>

      <ul className="divide-y divide-gray-200 rounded border border-gray-200 bg-white">
        {(data?.projects ?? []).map((p) => (
          <li key={p.id} className="flex items-center justify-between px-4 py-3">
            <div>
              <Link to={`/projects/${p.id}`} className="font-medium text-blue-700 hover:underline">
                {p.name}
              </Link>
              {p.series_brief && (
                <p className="text-xs text-gray-500">{p.series_brief}</p>
              )}
            </div>
            <span className="text-xs text-gray-400">{p.status}</span>
          </li>
        ))}
        {!data?.projects?.length && (
          <li className="px-4 py-6 text-center text-sm text-gray-400">暂无项目，先创建一个。</li>
        )}
      </ul>
    </div>
  )
}
