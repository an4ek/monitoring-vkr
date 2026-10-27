import { useSyncExternalStore } from 'react'

// Кто сейчас работает с системой. Входа в систему пока нет, поэтому сотрудника
// выбирают в шапке, а выбор запоминается в браузере (localStorage).
// Когда появится авторизация, этот хук будет брать пользователя с бэкенда.
const KEY = 'currentPersonId'
const listeners = new Set<() => void>()

function read(): number | null {
  try {
    const value = localStorage.getItem(KEY)
    return value ? Number(value) : null
  } catch {
    return null // в некоторых режимах браузера localStorage недоступен
  }
}

let current = read()

export function setCurrentUser(id: number) {
  current = id
  try {
    localStorage.setItem(KEY, String(id))
  } catch {
    // не запомнили — не страшно, выбор действует до перезагрузки страницы
  }
  listeners.forEach((notify) => notify())
}

export function useCurrentUser(): number | null {
  return useSyncExternalStore(
    (notify) => {
      listeners.add(notify)
      return () => listeners.delete(notify)
    },
    () => current,
  )
}
