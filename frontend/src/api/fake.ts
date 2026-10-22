// Имитация запроса к серверу: отдаёт данные с небольшой задержкой,
// чтобы на страницах было видно состояние загрузки, как с настоящим бэкендом.
export function fakeDelay<T>(data: T, ms = 300): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(data), ms))
}
