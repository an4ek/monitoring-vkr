// Модель данных системы. Те же сущности и поля будут в базе и в API бэкенда,
// поэтому имена полей пишем в snake_case — так их отдаёт Django.

export type Environment = 'prod' | 'test'
export type ResourceType = 'server' | 'database' | 'application' | 'network' | 'queue' | 'cache'
export type ServiceStatus = 'ok' | 'degraded' | 'down'
export type Severity = 'critical' | 'warning' | 'info'
export type IncidentStatus = 'open' | 'in_progress' | 'resolved'
export type EventSource = 'zabbix' | 'prometheus'

// Подразделение организации
export type Department = {
  id: number
  name: string
}

// Сотрудник, который может быть ответственным за сервис или ресурс
export type Person = {
  id: number
  full_name: string
  department_id: number
  email: string
  mattermost: string
}

// ИТ-сервис — то, чем пользуются сотрудники (CRM, почта, 1С...)
export type Service = {
  id: number
  name: string
  description: string
  department_id: number
  owner_id: number
  status: ServiceStatus
  slo_target: number // целевая доступность, %
  availability: number // фактическая доступность за 30 дней, %
}

// Ресурс — то, за чем следит мониторинг (сервер, база, приложение...)
export type Resource = {
  id: number
  name: string
  type: ResourceType
  environment: Environment
  description: string
  owner_id: number
  service_ids: number[] // каким сервисам нужен этот ресурс
  depends_on: number[] // от каких ресурсов он сам зависит
  runbook_url: string // инструкция: что делать при сбое
}

// Событие — один алерт, пришедший от Zabbix или Prometheus
export type MonitoringEvent = {
  id: number
  incident_id: number
  source: EventSource
  resource_id: number
  title: string
  severity: Severity
  received_at: string
}

// Запись в истории инцидента
export type IncidentHistoryItem = {
  at: string
  text: string
}

// Инцидент — несколько связанных событий, собранных в один сбой
export type Incident = {
  id: number
  title: string
  status: IncidentStatus
  severity: Severity
  root_cause_id: number // ресурс-первопричина
  affected_service_ids: number[]
  responsible_id: number
  assignee_id: number | null // кто взял в работу
  closed_by_id: number | null // кто закрыл вручную (пусто, если закрылся сам)
  started_at: string
  resolved_at: string | null
  history: IncidentHistoryItem[]
}

// Роли пользователей системы (диаграмма вариантов использования)
export type Role = 'admin' | 'engineer' | 'manager'

// Вошедший пользователь
export type Me = {
  username: string
  role: Role
  role_label: string
  person_id: number | null
  full_name: string
}
