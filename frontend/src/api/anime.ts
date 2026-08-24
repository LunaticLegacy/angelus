/** /api/anime/* 领域 API 封装。 */
import { api } from './client'
import type {
  AnimeEvent,
  Asset,
  DramaProject,
  Episode,
  GenerationJob,
  ProviderInfo,
  QAReport,
  Scene,
  Shot,
} from '@/types/anime'

// ---- projects ----
export const listProjects = () => api.get<{ projects: DramaProject[] }>('/api/anime/projects')
export const getProject = (id: string) => api.get<DramaProject>(`/api/anime/projects/${id}`)
export const createProject = (name: string, seriesBrief = '') =>
  api.post<DramaProject>('/api/anime/projects', { name, series_brief: seriesBrief })
export const updateProject = (id: string, patch: Partial<DramaProject>) =>
  api.put<DramaProject>(`/api/anime/projects/${id}`, patch)
export const deleteProject = (id: string) => api.delete<{ ok: boolean }>(`/api/anime/projects/${id}`)

// ---- episodes ----
export const listEpisodes = (projectId: string) =>
  api.get<{ episodes: Episode[] }>(`/api/anime/projects/${projectId}/episodes`)
export const createEpisode = (projectId: string, title: string, order = 0, outline = '') =>
  api.post<Episode>(`/api/anime/projects/${projectId}/episodes`, { title, order, outline })

// ---- scenes ----
export const listScenes = (projectId: string, episodeId: string) =>
  api.get<{ scenes: Scene[] }>(`/api/anime/projects/${projectId}/episodes/${episodeId}/scenes`)
export const createScene = (projectId: string, episodeId: string, title: string, order = 0, description = '') =>
  api.post<Scene>(`/api/anime/projects/${projectId}/episodes/${episodeId}/scenes`, {
    title,
    order,
    description,
  })

// ---- shots ----
export const listShots = (projectId: string, sceneId: string) =>
  api.get<{ shots: Shot[] }>(`/api/anime/projects/${projectId}/scenes/${sceneId}/shots`)
export const createShot = (projectId: string, sceneId: string, prompt: string, order = 0) =>
  api.post<Shot>(`/api/anime/projects/${projectId}/scenes/${sceneId}/shots`, { prompt, order })
export const transitionShot = (projectId: string, shotId: string, status: string) =>
  api.post<Shot>(`/api/anime/projects/${projectId}/shots/${shotId}/transition`, { status })
export const generateShot = (projectId: string, shotId: string, provider = 'mock') =>
  api.post<GenerationJob>(`/api/anime/projects/${projectId}/shots/${shotId}/generate`, { provider })

// ---- jobs ----
export const listJobs = (projectId: string) =>
  api.get<{ jobs: GenerationJob[] }>(`/api/anime/projects/${projectId}/jobs`)
export const cancelJob = (projectId: string, jobId: string) =>
  api.post<{ ok: boolean }>(`/api/anime/projects/${projectId}/jobs/${jobId}/cancel`)
export const retryJob = (projectId: string, jobId: string) =>
  api.post<{ ok: boolean; job: GenerationJob }>(`/api/anime/projects/${projectId}/jobs/${jobId}/retry`)

// ---- qa ----
export const listQa = (projectId: string) =>
  api.get<{ reports: QAReport[] }>(`/api/anime/projects/${projectId}/qa`)
export const runShotQa = (projectId: string, shotId: string, notes = '') =>
  api.post<QAReport>(`/api/anime/projects/${projectId}/shots/${shotId}/qa`, { notes })

// ---- providers ----
export const listProviders = () => api.get<{ providers: ProviderInfo[] }>('/api/anime/providers')

// ---- exports ----
export const exportFinalCut = (projectId: string, onlyApproved = true) =>
  api.get<{ project_id: string; shots: Shot[]; assets: Asset[] }>(
    `/api/anime/projects/${projectId}/export/final-cut?only_approved=${onlyApproved}`,
  )
export const exportScript = (projectId: string, episodeId?: string) =>
  api.get<{ project_id: string; episodes: unknown[] }>(
    `/api/anime/projects/${projectId}/export/script${episodeId ? `?episode_id=${episodeId}` : ''}`,
  )

// ---- events (SSE) ----
export function streamAnimeEvents(
  projectId: string,
  after: number,
  onEvent: (ev: AnimeEvent) => void,
  onError?: (err: unknown) => void,
): () => void {
  const es = new EventSource(`/api/anime/projects/${projectId}/events?after=${after}`)
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as AnimeEvent)
    } catch {
      /* ignore malformed frames */
    }
  }
  es.onerror = (err) => onError?.(err)
  return () => es.close()
}
