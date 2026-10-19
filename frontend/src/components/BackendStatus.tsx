import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../api/client.ts'

// Индикатор в шапке: отвечает ли бэкенд.
// useQuery сам делает запрос, повторяет его каждые 10 секунд
// и отдаёт нам состояние: загрузка / успех / ошибка.
export default function BackendStatus() {
  const { isPending, isError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10_000,
    retry: false,
  })

  let state = 'ok'
  let text = 'Бэкенд подключён'
  if (isPending) {
    state = 'pending'
    text = 'Проверяем бэкенд…'
  } else if (isError) {
    state = 'error'
    text = 'Бэкенд не отвечает'
  }

  return (
    <span className={`backend-status backend-status--${state}`}>
      <span className="backend-status__dot" />
      {text}
    </span>
  )
}
