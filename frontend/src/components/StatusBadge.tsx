/** 状态徽章：Shot / Job 状态着色。 */
import type { JobStatus, ShotStatus } from '@/types/anime'

const SHOT_COLORS: Record<string, string> = {
  DRAFT: 'gray',
  READY: 'blue',
  QUEUED: 'blue',
  GENERATING: 'amber',
  GENERATED: 'teal',
  QA_PENDING: 'violet',
  QA_PASSED: 'green',
  APPROVED: 'green',
  FAILED: 'red',
  RETRY_PENDING: 'orange',
}

const JOB_COLORS: Record<string, string> = {
  PENDING: 'gray',
  QUEUED: 'blue',
  RUNNING: 'amber',
  SUCCEEDED: 'green',
  FAILED: 'red',
  CANCELLED: 'gray',
  EXPIRED: 'gray',
}

const PALETTE: Record<string, string> = {
  gray: 'bg-gray-100 text-gray-700',
  blue: 'bg-blue-100 text-blue-700',
  amber: 'bg-amber-100 text-amber-700',
  teal: 'bg-teal-100 text-teal-700',
  violet: 'bg-violet-100 text-violet-700',
  green: 'bg-green-100 text-green-700',
  red: 'bg-red-100 text-red-700',
  orange: 'bg-orange-100 text-orange-700',
}

export function ShotStatusBadge({ status }: { status: ShotStatus }) {
  const color = PALETTE[SHOT_COLORS[status] ?? 'gray']
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>{status}</span>
  )
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const color = PALETTE[JOB_COLORS[status] ?? 'gray']
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>{status}</span>
  )
}
