// Вход и выход. Сессия хранится в cookie, которую JavaScript прочитать не может.
import { apiGet, apiPost } from './client.ts'
import type { Me } from '../types.ts'

export const fetchMe = () => apiGet<Me>('/auth/me/')

export async function login(username: string, password: string) {
  await apiGet('/auth/csrf/') // получить CSRF-cookie, без неё вход не пройдёт
  return apiPost<Me>('/auth/login/', { username, password })
}

export const logout = () => apiPost('/auth/logout/')
