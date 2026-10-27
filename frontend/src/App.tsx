import { Navigate, Route, Routes } from 'react-router'
import Layout from './components/Layout.tsx'
import RequireAuth from './components/RequireAuth.tsx'
import LoginPage from './pages/LoginPage.tsx'
import IncidentsPage from './pages/IncidentsPage.tsx'
import IncidentDetailPage from './pages/IncidentDetailPage.tsx'
import ServicesPage from './pages/ServicesPage.tsx'
import CatalogPage from './pages/CatalogPage.tsx'
import SubscriptionsPage from './pages/SubscriptionsPage.tsx'
import NotFoundPage from './pages/NotFoundPage.tsx'

// Карта страниц: какой адрес какую страницу показывает.
// Страница входа открыта всем, остальные — только после входа (RequireAuth)
// и рисуются внутри Layout (меню слева + шапка).
export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/incidents" replace />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/:id" element={<IncidentDetailPage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="subscriptions" element={<SubscriptionsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      </Route>
    </Routes>
  )
}
