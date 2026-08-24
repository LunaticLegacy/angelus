/** 全局 UI 状态：当前项目 / 剧集 / 场景选择 + 事件流。 */
import { create } from 'zustand'
import type { AnimeEvent } from '@/types/anime'

interface StudioState {
  projectId: string | null
  episodeId: string | null
  sceneId: string | null
  events: AnimeEvent[]
  setProject: (id: string | null) => void
  setEpisode: (id: string | null) => void
  setScene: (id: string | null) => void
  pushEvent: (ev: AnimeEvent) => void
  clearEvents: () => void
}

export const useStudioStore = create<StudioState>((set) => ({
  projectId: null,
  episodeId: null,
  sceneId: null,
  events: [],
  setProject: (id) => set({ projectId: id, episodeId: null, sceneId: null }),
  setEpisode: (id) => set({ episodeId: id, sceneId: null }),
  setScene: (id) => set({ sceneId: id }),
  pushEvent: (ev) =>
    set((s) => ({ events: [...s.events.slice(-499), ev] })),
  clearEvents: () => set({ events: [] }),
}))
