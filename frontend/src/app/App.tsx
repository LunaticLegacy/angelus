/** 应用路由：Studio 布局 + 页面。 */
import { Navigate, Route, Routes } from 'react-router-dom'
import { StudioLayout } from '@/layouts/StudioLayout'
import { ProjectsPage } from '@/pages/ProjectsPage'
import { ProjectDetailPage } from '@/pages/ProjectDetailPage'
import { JobsPage } from '@/pages/JobsPage'
import { EventsPage } from '@/pages/EventsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<StudioLayout />}>
        <Route index element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/projects/:projectId/jobs" element={<JobsPage />} />
        <Route path="/projects/:projectId/events" element={<EventsPage />} />
      </Route>
    </Routes>
  )
}
