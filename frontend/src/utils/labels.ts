// Русские подписи и цвета для значений из модели данных.
import type {
  Environment,
  EventSource,
  IncidentStatus,
  ResourceType,
  ServiceStatus,
  Severity,
} from '../types.ts'

export const incidentStatusLabels: Record<IncidentStatus, { text: string; color: string }> = {
  open: { text: 'Открыт', color: 'red' },
  in_progress: { text: 'В работе', color: 'orange' },
  resolved: { text: 'Закрыт', color: 'green' },
}

export const severityLabels: Record<Severity, { text: string; color: string }> = {
  critical: { text: 'Критично', color: 'red' },
  warning: { text: 'Предупреждение', color: 'gold' },
  info: { text: 'Информация', color: 'blue' },
}

export const serviceStatusLabels: Record<ServiceStatus, { text: string; color: string }> = {
  ok: { text: 'Работает', color: 'green' },
  degraded: { text: 'С проблемами', color: 'orange' },
  down: { text: 'Не работает', color: 'red' },
}

export const resourceTypeLabels: Record<ResourceType, string> = {
  server: 'Сервер',
  database: 'База данных',
  application: 'Приложение',
  network: 'Сеть',
  queue: 'Очередь',
  cache: 'Кэш',
}

export const environmentLabels: Record<Environment, { text: string; color: string }> = {
  prod: { text: 'prod', color: 'purple' },
  test: { text: 'test', color: 'default' },
}

export const sourceLabels: Record<EventSource, string> = {
  zabbix: 'Zabbix',
  prometheus: 'Prometheus',
}
