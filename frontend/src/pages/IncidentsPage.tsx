import { useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Segmented, Space, Table, Tag } from 'antd'
import type { TableProps } from 'antd'
import { fetchIncidents } from '../api/incidents.ts'
import { useCatalog } from '../hooks/useCatalog.ts'
import { IncidentStatusTag, SeverityTag } from '../components/StatusTags.tsx'
import { formatDateTime, formatDuration } from '../utils/format.ts'
import type { Incident, IncidentStatus } from '../types.ts'

type Filter = 'all' | IncidentStatus

// Список инцидентов: каждый сбой одной строкой, сверху фильтр по статусу
export default function IncidentsPage() {
  const [filter, setFilter] = useState<Filter>('all')
  // Обновляем список каждые 5 секунд: новый инцидент появляется сам, без перезагрузки
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: fetchIncidents, refetchInterval: 5_000 })
  const catalog = useCatalog()

  const rows = (incidents.data ?? [])
    .filter((item) => filter === 'all' || item.status === filter)
    .sort((a, b) => b.started_at.localeCompare(a.started_at))

  const columns: TableProps<Incident>['columns'] = [
    { title: '№', dataIndex: 'id', width: 60 },
    {
      title: 'Инцидент',
      dataIndex: 'title',
      render: (title: string, incident) => <Link to={`/incidents/${incident.id}`}>{title}</Link>,
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      render: (status: IncidentStatus) => <IncidentStatusTag status={status} />,
    },
    {
      title: 'Важность',
      dataIndex: 'severity',
      render: (_, incident) => <SeverityTag severity={incident.severity} />,
    },
    {
      title: 'Первопричина',
      dataIndex: 'root_cause_id',
      render: (id: number) => catalog.resourcesById.get(id)?.name ?? '—',
    },
    {
      title: 'Затронутые сервисы',
      dataIndex: 'affected_service_ids',
      render: (ids: number[]) => (
        <Space size={[0, 4]} wrap>
          {ids.map((id) => (
            <Tag key={id}>{catalog.servicesById.get(id)?.name}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: 'Начало',
      dataIndex: 'started_at',
      render: (value: string) => formatDateTime(value),
    },
    {
      title: 'Длительность',
      key: 'duration',
      render: (_, incident) => formatDuration(incident.started_at, incident.resolved_at),
    },
  ]

  return (
    <>
      <h1>Инциденты</h1>
      <Segmented<Filter>
        style={{ margin: '8px 0 16px' }}
        value={filter}
        onChange={setFilter}
        options={[
          { label: 'Все', value: 'all' },
          { label: 'Открытые', value: 'open' },
          { label: 'В работе', value: 'in_progress' },
          { label: 'Закрытые', value: 'resolved' },
        ]}
      />
      <Table<Incident>
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={incidents.isPending || catalog.isPending}
        pagination={false}
      />
    </>
  )
}
