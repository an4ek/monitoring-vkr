// Запросы инцидентов и событий. Пока из тестовых данных, как и каталог.
// import { events, incidents } from '../mocks/data.ts'
// import { fakeDelay } from './fake.ts'

// export const fetchIncidents = () => fakeDelay(incidents)

// export function fetchIncident(id: number) {
//   const incident = incidents.find((item) => item.id === id)
//   if (!incident) {
//     return Promise.reject(new Error('Инцидент не найден'))
//   }
//   return fakeDelay(incident)
// }

// export const fetchIncidentEvents = (incidentId: number) =>
//   fakeDelay(events.filter((event) => event.incident_id === incidentId))


// Запросы инцидентов и событий — с реального бэкенда.
import { apiGet, apiPost } from './client.ts'
import type { Incident, MonitoringEvent } from '../types.ts'

export const fetchIncidents = () => apiGet<Incident[]>('/incidents/')

export const fetchIncident = (id: number) => apiGet<Incident>(`/incidents/${id}/`)

export const fetchIncidentEvents = (incidentId: number) =>
  apiGet<MonitoringEvent[]>(`/incidents/${incidentId}/events/`)

// Разбор инцидента. Пока нет входа в систему, передаём, кто нажал кнопку (personId).
export const takeIncident = (id: number, personId: number) =>
  apiPost<Incident>(`/incidents/${id}/take/`, { person_id: personId })

export const closeIncident = (id: number, personId: number, comment: string) =>
  apiPost<Incident>(`/incidents/${id}/close/`, { person_id: personId, comment })
