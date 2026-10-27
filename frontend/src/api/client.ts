// Общая функция для запросов к бэкенду.
// Адрес начинается с /api — Vite перешлёт его в Django (см. vite.config.ts).
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`)
  if (!response.ok) {
    throw new Error(`Ошибка ${response.status} при запросе ${path}`)
  }
  return response.json() as Promise<T>
}

// CSRF-токен: Django кладет его в cookie csrftoken, а изменяющие запросы
// должны повторить его в заголовке X-CSRFToken. Так чужой сайт не сможет
// нажать кнопку от имени вошедшего пользователя.
function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// Отправка данных на бэкенд (вход, «Взять в работу», «Закрыть» и т. п.).
// Если бэкенд вернул ошибку, показываем его объяснение (поле detail).
export async function apiSend<T>(method: 'POST' | 'DELETE', path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail ?? `Ошибка ${response.status} при запросе ${path}`)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const apiPost = <T>(path: string, body?: unknown) => apiSend<T>('POST', path, body)

// Проверка, что бэкенд жив: Django отвечает на /api/health/.
export type Health = { status: string }

export function fetchHealth() {
  return apiGet<Health>('/health/')
}
