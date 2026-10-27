// Подписки: сотрудник просит сообщать ему о сбоях сервиса, даже если он за него не отвечает.
// Бэкенд отдаёт и меняет только подписки вошедшего пользователя.
import { apiDelete, apiGet, apiPost } from './client.ts'

export type Subscription = { id: number; person_id: number; service_id: number; created_at: string }

export const fetchSubscriptions = () => apiGet<Subscription[]>('/subscriptions/')
export const subscribe = (serviceId: number) => apiPost<Subscription>('/subscriptions/', { service_id: serviceId })
export const unsubscribe = (id: number) => apiDelete(`/subscriptions/${id}/`)
