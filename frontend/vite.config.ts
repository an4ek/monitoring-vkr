import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Все запросы на /api/... Vite пересылает в Django (бэкенд Лизы).
    // Поэтому во фронтенде пишем просто fetch('/api/...'), без адреса сервера.
    // /admin и /static — админка Django для администратора системы.
    proxy: {
      '/api': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
    },
  },
})
