import { NavLink, Outlet } from 'react-router'
import BackendStatus from './BackendStatus.tsx'

const menu = [
  { to: '/incidents', label: 'Инциденты' },
  { to: '/services', label: 'Сервисы' },
  { to: '/catalog', label: 'Каталог' },
  { to: '/subscriptions', label: 'Подписки' },
]

// Общий каркас всех страниц: меню слева, шапка сверху,
// а на место <Outlet /> подставляется текущая страница.
export default function Layout() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar__logo">Мониторинг</div>
        <nav className="sidebar__nav">
          {menu.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? 'sidebar__link sidebar__link--active' : 'sidebar__link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="main">
        <header className="header">
          <BackendStatus />
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
