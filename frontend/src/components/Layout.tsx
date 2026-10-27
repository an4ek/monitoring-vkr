import { NavLink, Outlet, useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Button, Tag } from 'antd'
import BackendStatus from './BackendStatus.tsx'
import { logout } from '../api/auth.ts'
import { useAuth } from '../hooks/useAuth.ts'

const menu = [
  { to: '/incidents', label: 'Инциденты' },
  { to: '/services', label: 'Сервисы' },
  { to: '/catalog', label: 'Каталог' },
  { to: '/subscriptions', label: 'Подписки' },
]

// Общий каркас всех страниц: меню слева, шапка сверху,
// а на место <Outlet /> подставляется текущая страница.
export default function Layout() {
  const { me } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const onLogout = async () => {
    await logout().catch(() => undefined)
    queryClient.clear() // стираем данные из памяти страницы
    navigate('/login', { replace: true })
  }

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
          {/* Данные приходят с бэкенда, но в базе пока тестовый каталог — честно показываем это */}
          <Tag color="gold">Тестовые данные</Tag>
          <BackendStatus />
          {me && (
            <span className="header__user">
              {me.full_name}
              <Tag>{me.role_label}</Tag>
              <Button size="small" onClick={onLogout}>
                Выйти
              </Button>
            </span>
          )}
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
