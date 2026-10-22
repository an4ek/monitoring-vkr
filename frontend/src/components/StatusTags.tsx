import { Tag } from 'antd'
import type { IncidentStatus, ServiceStatus, Severity } from '../types.ts'
import { incidentStatusLabels, serviceStatusLabels, severityLabels } from '../utils/labels.ts'

// Цветные метки статусов. Используются на всех страницах, чтобы цвета везде совпадали.

export function IncidentStatusTag({ status }: { status: IncidentStatus }) {
  const label = incidentStatusLabels[status]
  return <Tag color={label.color}>{label.text}</Tag>
}

export function SeverityTag({ severity }: { severity: Severity }) {
  const label = severityLabels[severity]
  return <Tag color={label.color}>{label.text}</Tag>
}

export function ServiceStatusTag({ status }: { status: ServiceStatus }) {
  const label = serviceStatusLabels[status]
  return <Tag color={label.color}>{label.text}</Tag>
}
