import { Navigate, Outlet, useLocation } from 'react-router'
import { Spin } from 'antd'
import { useAuth } from '../hooks/useAuth.ts'

// Пускает на страницы системы только после входа, иначе отправляет на страницу входа
export default function RequireAuth() {
  const { isPending, me } = useAuth()
  const location = useLocation()

  if (isPending) {
    return <Spin style={{ margin: 48 }} />
  }
  if (!me) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}
