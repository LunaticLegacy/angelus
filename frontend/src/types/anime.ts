/** 领域类型：与 angelus/anime/models.py + states.py 一一对应。 */

export type ShotStatus =
  | 'DRAFT'
  | 'READY'
  | 'QUEUED'
  | 'GENERATING'
  | 'GENERATED'
  | 'QA_PENDING'
  | 'QA_PASSED'
  | 'APPROVED'
  | 'FAILED'
  | 'RETRY_PENDING'

export type JobStatus =
  | 'PENDING'
  | 'QUEUED'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED'
  | 'EXPIRED'

export type GateVerdict = 'PASS' | 'WARN' | 'FAIL'

export interface DramaProject {
  id: string
  name: string
  series_brief: string
  global_outline: string
  created_at: number
  updated_at: number
  status: 'DRAFT' | 'ACTIVE' | 'ARCHIVED'
}

export interface Episode {
  id: string
  project_id: string
  title: string
  order: number
  arc_id: string
  outline: string
  status: string
  created_at: number
  updated_at: number
}

export interface Scene {
  id: string
  episode_id: string
  project_id: string
  title: string
  order: number
  description: string
  location: string
  status: string
  created_at: number
  updated_at: number
}

export interface Shot {
  id: string
  scene_id: string
  episode_id: string
  project_id: string
  order: number
  prompt: string
  negative_prompt: string
  duration_seconds: number
  status: ShotStatus
  asset_id: string | null
  retry_count: number
  error: string | null
  created_at: number
  updated_at: number
}

export interface Asset {
  id: string
  project_id: string
  kind: 'video' | 'image' | 'audio' | 'subtitle' | 'script' | 'storyboard'
  uri: string
  mime_type: string
  size_bytes: number
  meta: Record<string, unknown>
  created_at: number
}

export interface GenerationJob {
  id: string
  project_id: string
  shot_id: string
  provider: string
  status: JobStatus
  params: Record<string, unknown>
  result_asset_id: string | null
  error: string | null
  retry_count: number
  max_retries: number
  created_at: number
  updated_at: number
  started_at: number | null
  finished_at: number | null
}

export interface QAReport {
  id: string
  project_id: string
  shot_id: string
  verdict: GateVerdict
  checks: Array<{ name: string; verdict: GateVerdict; detail: string }>
  notes: string
  created_at: number
}

export interface ProviderInfo {
  name: string
  capabilities: Record<string, unknown>
}

export interface AnimeEvent {
  seq: number
  type: string
  ts: number
  payload: Record<string, unknown>
}
