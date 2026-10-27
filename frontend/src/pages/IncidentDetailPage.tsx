import { Link, useParams } from 'react-router'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Card, Col, Descriptions, Input, Modal, Result, Row, Space, Spin, Table, Tag, Timeline } from 'antd'
import type { TableProps } from 'antd'
import { closeIncident, fetchIncident, fetchIncidentEvents, takeIncident } from '../api/incidents.ts'
import { useCurrentUser } from '../hooks/useCurrentUser.ts'
import { useCatalog } from '../hooks/useCatalog.ts'
import { IncidentStatusTag, ServiceStatusTag, SeverityTag } from '../components/StatusTags.tsx'
import { formatDateTime, formatDuration, formatTime } from '../utils/format.ts'
import { resourceTypeLabels, sourceLabels } from '../utils/labels.ts'
import type { MonitoringEvent, Severity } from '../types.ts'

// Карточка инцидента: главное — что сломалось первым (первопричина)
// и какие события и сервисы пострадали из-за этого (следствия).
export default function IncidentDetailPage() {
  const id = Number(useParams().id)
  const incident = useQuery({
    queryKey: ['incident', id],
    queryFn: () => fetchIncident(id),
    retry: false, // если инцидента нет, сразу показываем «не найден», без повторных попыток
    refetchInterval: 5_000, // новые события и смена первопричины видны сразу
  })
  const events = useQuery({ queryKey: ['events', id], queryFn: () => fetchIncidentEvents(id), refetchInterval: 5_000 })
  const catalog = useCatalog()

  // Кнопки «Взять в работу» и «Закрыть»
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const currentUser = useCurrentUser()
  const [closeOpen, setCloseOpen] = useState(false)
  const [comment, setComment] = useState('')

  const onDone = (text: string) => {
    message.success(text)
    queryClient.invalidateQueries({ queryKey: ['incident', id] })
    queryClient.invalidateQueries({ queryKey: ['incidents'] })
  }
  const take = useMutation({
    mutationFn: () => takeIncident(id, currentUser!),
    onSuccess: () => onDone('Инцидент взят в работу'),
    onError: (error) => message.error(error.message),
  })
  const close = useMutation({
    mutationFn: () => closeIncident(id, currentUser!, comment),
    onSuccess: () => {
      setCloseOpen(false)
      setComment('')
      onDone('Инцидент закрыт')
    },
    onError: (error) => message.error(error.message),
  })

  if (incident.isError) {
    return (
      <Result
        status="404"
        title="Инцидент не найден"
        extra={<Link to="/incidents">К списку инцидентов</Link>}
      />
    )
  }

  if (incident.isPending || catalog.isPending) {
    return <Spin />
  }

  const data = incident.data
  const rootCause = catalog.resourcesById.get(data.root_cause_id)
  const responsible = catalog.peopleById.get(data.responsible_id)

  const eventColumns: TableProps<MonitoringEvent>['columns'] = [
    { title: 'Время', dataIndex: 'received_at', render: (value: string) => formatTime(value) },
    {
      title: 'Ресурс',
      dataIndex: 'resource_id',
      render: (resourceId: number) => catalog.resourcesById.get(resourceId)?.name,
    },
    { title: 'Событие', dataIndex: 'title' },
    { title: 'Источник', dataIndex: 'source', render: (source: MonitoringEvent['source']) => sourceLabels[source] },
    {
      title: 'Важность',
      dataIndex: 'severity',
      render: (severity: Severity) => <SeverityTag severity={severity} />,
    },
    {
      title: 'Роль',
      key: 'role',
      render: (_, event) =>
        event.resource_id === data.root_cause_id ? (
          <Tag color="red">Первопричина</Tag>
        ) : (
          <Tag>Следствие</Tag>
        ),
    },
  ]

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Link to="/incidents">← Все инциденты</Link>

      <div>
        <h1>
          Инцидент №{data.id}. {data.title}
        </h1>
        <Space>
          <IncidentStatusTag status={data.status} />
          <SeverityTag severity={data.severity} />
        </Space>
      </div>

      {data.status !== 'resolved' && (
        <Space>
          {data.status === 'open' && (
            <Button type="primary" disabled={!currentUser} loading={take.isPending} onClick={() => take.mutate()}>
              Взять в работу
            </Button>
          )}
          <Button disabled={!currentUser} onClick={() => setCloseOpen(true)}>
            Закрыть
          </Button>
          {!currentUser && <span className="hint">Выберите себя в шапке справа, чтобы работать с инцидентом</span>}
        </Space>
      )}

      <Modal
        title={`Закрыть инцидент №${data.id}`}
        open={closeOpen}
        okText="Закрыть инцидент"
        cancelText="Отмена"
        confirmLoading={close.isPending}
        onOk={() => close.mutate()}
        onCancel={() => setCloseOpen(false)}
      >
        <p>Обычно инцидент закрывается сам, когда мониторинг сообщает, что все ресурсы восстановились. Закрыть вручную нужно, если такого сообщения не будет или сбой оказался ложным.</p>
        <Input.TextArea
          rows={3}
          placeholder="Что сделано (необязательно)"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </Modal>

      {rootCause && (
        <Alert
          type="error"
          showIcon
          title={`Первопричина: ${rootCause.name} — ${rootCause.description}`}
          description={`${resourceTypeLabels[rootCause.type]}. Остальные события в инциденте — следствия этого сбоя.`}
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="Сведения">
            <Descriptions
              column={1}
              items={[
                { label: 'Ответственный', children: responsible?.full_name ?? '—' },
                { label: 'Контакты', children: responsible ? `${responsible.mattermost}, ${responsible.email}` : '—' },
                { label: 'Начало', children: formatDateTime(data.started_at) },
                { label: 'Длительность', children: formatDuration(data.started_at, data.resolved_at) },
                {
                  label: 'Инструкция',
                  children: rootCause ? (
                    <a href={rootCause.runbook_url} target="_blank" rel="noreferrer">
                      {rootCause.runbook_url}
                    </a>
                  ) : (
                    '—'
                  ),
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Затронутые сервисы">
            <Space orientation="vertical">
              {data.affected_service_ids.map((serviceId) => {
                const service = catalog.servicesById.get(serviceId)
                if (!service) return null
                return (
                  <Space key={service.id}>
                    <span>{service.name}</span>
                    <ServiceStatusTag status={service.status} />
                  </Space>
                )
              })}
            </Space>
          </Card>
        </Col>
      </Row>

      <Card title={`События (${events.data?.length ?? 0})`}>
        <Table<MonitoringEvent>
          rowKey="id"
          columns={eventColumns}
          dataSource={events.data ?? []}
          loading={events.isPending}
          pagination={false}
          size="small"
        />
      </Card>

      <Card title="История">
        <Timeline
          items={data.history.map((item) => ({
            content: (
              <>
                <div className="hint">{formatDateTime(item.at)}</div>
                {item.text}
              </>
            ),
          }))}
        />
      </Card>
    </Space>
  )
}
