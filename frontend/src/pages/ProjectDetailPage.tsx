/** 项目详情：剧集 → 场景 → 镜头 树 + 生成/QA 操作。 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createEpisode,
  createScene,
  createShot,
  generateShot,
  getProject,
  listEpisodes,
  listScenes,
  listShots,
  runShotQa,
  transitionShot,
} from '@/api/anime'
import { ShotStatusBadge } from '@/components/StatusBadge'
import { useAnimeEvents } from '@/hooks/useAnimeEvents'
import { useStudioStore } from '@/stores/studio'

export function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const qc = useQueryClient()
  const { setProject, setEpisode, setScene } = useStudioStore()
  const [epTitle, setEpTitle] = useState('')
  const [scTitle, setScTitle] = useState('')
  const [shotPrompt, setShotPrompt] = useState('')

  useAnimeEvents(projectId)

  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => getProject(projectId) })
  const episodes = useQuery({
    queryKey: ['episodes', projectId],
    queryFn: () => listEpisodes(projectId),
  })
  const [openEp, setOpenEp] = useState<string | null>(null)
  const [openSc, setOpenSc] = useState<string | null>(null)

  const scenes = useQuery({
    queryKey: ['scenes', projectId, openEp ?? ''],
    queryFn: () => listScenes(projectId, openEp!),
    enabled: !!openEp,
  })
  const shots = useQuery({
    queryKey: ['shots', projectId, openSc ?? ''],
    queryFn: () => listShots(projectId, openSc!),
    enabled: !!openSc,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['episodes', projectId] })
    qc.invalidateQueries({ queryKey: ['scenes', projectId] })
    qc.invalidateQueries({ queryKey: ['shots', projectId] })
  }

  const addEpisode = useMutation({
    mutationFn: () => createEpisode(projectId, epTitle, (episodes.data?.episodes.length ?? 0) + 1),
    onSuccess: () => {
      setEpTitle('')
      invalidate()
    },
  })
  const addScene = useMutation({
    mutationFn: () =>
      createScene(projectId, openEp!, scTitle, (scenes.data?.scenes.length ?? 0) + 1),
    onSuccess: () => {
      setScTitle('')
      invalidate()
    },
  })
  const addShot = useMutation({
    mutationFn: () =>
      createShot(projectId, openSc!, shotPrompt, (shots.data?.shots.length ?? 0) + 1),
    onSuccess: () => {
      setShotPrompt('')
      invalidate()
    },
  })
  const gen = useMutation({
    mutationFn: ({ pid, sid }: { pid: string; sid: string }) => generateShot(pid, sid),
    onSuccess: invalidate,
  })
  const qa = useMutation({
    mutationFn: ({ pid, sid }: { pid: string; sid: string }) => runShotQa(pid, sid),
    onSuccess: invalidate,
  })
  const trans = useMutation({
    mutationFn: ({ pid, sid, status }: { pid: string; sid: string; status: string }) =>
      transitionShot(pid, sid, status),
    onSuccess: invalidate,
  })

  return (
    <div className="max-w-5xl">
      <Link to="/projects" className="text-sm text-blue-600 hover:underline">
        ← 返回项目列表
      </Link>
      <h2 className="mt-2 mb-1 text-xl font-semibold">{project.data?.name ?? '项目'}</h2>
      {project.data?.series_brief && (
        <p className="mb-4 text-sm text-gray-500">{project.data.series_brief}</p>
      )}
      <div className="mb-4 flex gap-2 text-sm">
        <Link to={`/projects/${projectId}/jobs`} className="text-blue-600 hover:underline">
          生成任务
        </Link>
        <span className="text-gray-300">|</span>
        <Link to={`/projects/${projectId}/events`} className="text-blue-600 hover:underline">
          事件流
        </Link>
      </div>

      {/* 新建剧集 */}
      <form
        className="mb-4 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (epTitle.trim()) addEpisode.mutate()
        }}
      >
        <input
          className="flex-1 rounded border border-gray-300 px-3 py-2 text-sm"
          placeholder="新剧集标题"
          value={epTitle}
          onChange={(e) => setEpTitle(e.target.value)}
        />
        <button
          type="submit"
          disabled={!epTitle.trim()}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
        >
          添加剧集
        </button>
      </form>

      <div className="space-y-2">
        {(episodes.data?.episodes ?? []).map((ep) => (
          <div key={ep.id} className="rounded border border-gray-200 bg-white">
            <button
              className="flex w-full items-center justify-between px-4 py-3 text-left"
              onClick={() => {
                setProject(projectId)
                setEpisode(ep.id)
                setOpenEp((cur) => (cur === ep.id ? null : ep.id))
              }}
            >
              <span className="font-medium">
                EP{ep.order} · {ep.title}
              </span>
              <span className="text-xs text-gray-400">{ep.status}</span>
            </button>

            {openEp === ep.id && (
              <div className="border-t border-gray-100 px-4 py-3">
                <form
                  className="mb-3 flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (scTitle.trim()) addScene.mutate()
                  }}
                >
                  <input
                    className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
                    placeholder="新场景标题"
                    value={scTitle}
                    onChange={(e) => setScTitle(e.target.value)}
                  />
                  <button
                    type="submit"
                    disabled={!scTitle.trim()}
                    className="rounded bg-gray-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                  >
                    添加场景
                  </button>
                </form>

                <div className="space-y-2">
                  {(scenes.data?.scenes ?? []).map((sc) => (
                    <div key={sc.id} className="rounded border border-gray-100 bg-gray-50">
                      <button
                        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm"
                        onClick={() => {
                          setScene(sc.id)
                          setOpenSc((cur) => (cur === sc.id ? null : sc.id))
                        }}
                      >
                        <span className="font-medium">场景{sc.order} · {sc.title}</span>
                        <span className="text-xs text-gray-400">{sc.location || '—'}</span>
                      </button>

                      {openSc === sc.id && (
                        <div className="border-t border-gray-100 px-3 py-2">
                          <form
                            className="mb-2 flex gap-2"
                            onSubmit={(e) => {
                              e.preventDefault()
                              if (shotPrompt.trim()) addShot.mutate()
                            }}
                          >
                            <input
                              className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
                              placeholder="镜头 prompt"
                              value={shotPrompt}
                              onChange={(e) => setShotPrompt(e.target.value)}
                            />
                            <button
                              type="submit"
                              disabled={!shotPrompt.trim()}
                              className="rounded bg-gray-700 px-3 py-1.5 text-sm text-white disabled:opacity-50"
                            >
                              添加镜头
                            </button>
                          </form>

                          <ul className="space-y-1.5">
                            {(shots.data?.shots ?? []).map((sh) => (
                              <li key={sh.id} className="flex items-center gap-2 rounded border border-gray-200 bg-white px-3 py-2 text-sm">
                                <span className="w-10 text-gray-400">#{sh.order}</span>
                                <span className="flex-1 truncate">{sh.prompt || '（无 prompt）'}</span>
                                <ShotStatusBadge status={sh.status} />
                                <button
                                  className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700"
                                  onClick={() => gen.mutate({ pid: projectId, sid: sh.id })}
                                >
                                  生成
                                </button>
                                <button
                                  className="rounded bg-violet-600 px-2 py-1 text-xs text-white hover:bg-violet-700"
                                  onClick={() => qa.mutate({ pid: projectId, sid: sh.id })}
                                >
                                  QA
                                </button>
                                <button
                                  className="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                                  onClick={() =>
                                    trans.mutate({ pid: projectId, sid: sh.id, status: 'APPROVED' })
                                  }
                                >
                                  通过
                                </button>
                              </li>
                            ))}
                            {!shots.data?.shots?.length && (
                              <li className="text-xs text-gray-400">暂无镜头</li>
                            )}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))}
                  {!scenes.data?.scenes?.length && (
                    <p className="text-xs text-gray-400">暂无场景</p>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {!episodes.data?.episodes?.length && (
          <p className="text-sm text-gray-400">暂无剧集，先添加一集。</p>
        )}
      </div>
    </div>
  )
}
