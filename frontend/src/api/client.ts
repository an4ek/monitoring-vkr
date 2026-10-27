// Общая функция для запросов к бэкенду.
// Адрес начинается с /api — Vite перешлёт его в Django (см. vite.config.ts).
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  if (!response.ok) {
    throw new Error(`Ошибка ${response.status} при запросе ${path}`)
  }
  return response.json() as Promise<T>
}

// Отправка данных на бэкенд (кнопки «Взять в работу», «Закрыть» и т. п.).
// Если бэкенд вернул ошибку, показываем его объяснение (поле detail).
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail ?? `Ошибка ${response.status} при запросе ${path}`)
  }
  return response.json() as Promise<T>
}

// Проверка, что бэкенд жив: Django отвечает на /api/health/.
export type Health = { status: string }

export function fetchHealth() {
  return apiGet<Health>('/health/')
}
