import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import ruRU from 'antd/locale/ru_RU'
import App from './App.tsx'
import './index.css'

// QueryClient хранит загруженные с бэкенда данные (кэш) и следит, когда их обновлять.
const queryClient = new QueryClient()

// ConfigProvider настраивает компоненты Ant Design: русский язык и основной цвет.
// AntApp нужен, чтобы всплывающие сообщения («Инцидент закрыт») брали эти настройки.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={ruRU} theme={{ token: { colorPrimary: '#2f6feb' } }}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
)
