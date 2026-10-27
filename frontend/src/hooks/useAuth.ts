import { useQuery } from '@tanstack/react-query'
import { fetchMe } from '../api/auth.ts'

// Кто сейчас вошёл. Если бэкенд ответил ошибкой — значит, вход не выполнен.
export function useAuth() {
  const me = useQuery({ queryKey: ['me'], queryFn: fetchMe, retry: false, staleTime: 60_000 })
  return {
    isPending: me.isPending,
    me: me.data ?? null,
    isEngineer: me.data?.role === 'engineer',
  }
}
