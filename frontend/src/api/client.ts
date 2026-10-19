// Общая функция для запросов к бэкенду.
// Адрес начинается с /api — Vite перешлёт его в Django (см. vite.config.ts).
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  if (!response.ok) {
    throw new Error(`Ошибка ${response.status} при запросе ${path}`)
  }
  return response.json() as Promise<T>
}

// Проверка, что бэкенд жив. Лиза делает в Django адрес /api/health/.
export type Health = { status: string }

export function fetchHealth() {
  return apiGet<Health>('/health/')
}
