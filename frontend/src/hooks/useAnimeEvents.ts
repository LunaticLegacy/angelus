/** 订阅项目 SSE 事件流，写入 Zustand。 */
import { useEffect } from 'react'
import { streamAnimeEvents } from '@/api/anime'
import { useStudioStore } from '@/stores/studio'

export function useAnimeEvents(projectId: string | null) {
  const pushEvent = useStudioStore((s) => s.pushEvent)
  useEffect(() => {
    if (!projectId) return
    const close = streamAnimeEvents(projectId, 0, pushEvent)
    return close
  }, [projectId, pushEvent])
}
