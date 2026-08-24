/** Studio 布局：侧栏导航 + 主内容区。 */
import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/projects', label: '项目' },
]

export function StudioLayout() {
  return (
    <div className="flex h-screen bg-gray-50 text-gray-900">
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white p-4">
        <h1 className="mb-4 text-sm font-bold tracking-wide text-gray-700">
          Angelus Studio
        </h1>
        <nav className="space-y-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded px-3 py-2 text-sm ${
                  isActive ? 'bg-blue-50 font-medium text-blue-700' : 'text-gray-600 hover:bg-gray-100'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
