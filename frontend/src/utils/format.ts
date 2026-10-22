// Форматирование дат и длительностей для таблиц и карточек.

export function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// Длительность сбоя: от начала до закрытия, а если ещё не закрыт — до текущего момента
export function formatDuration(from: string, to: string | null) {
  const end = to ? new Date(to) : new Date()
  const minutes = Math.max(0, Math.round((end.getTime() - new Date(from).getTime()) / 60000))
  if (minutes < 60) return `${minutes} мин`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} ч ${minutes % 60} мин`
  return `${Math.floor(hours / 24)} д ${hours % 24} ч`
}

// Проценты по-русски: 99,92 %
export function formatPercent(value: number) {
  return `${value.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} %`
}
