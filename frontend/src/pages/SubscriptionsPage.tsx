import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, Col, Result, Row, Space, Table, Tag } from 'antd'
import type { TableProps } from 'antd'
import { fetchSubscriptions, subscribe, unsubscribe } from '../api/subscriptions.ts'
import { useAuth } from '../hooks/useAuth.ts'
import { useCatalog } from '../hooks/useCatalog.ts'
import { ServiceStatusTag } from '../components/StatusTags.tsx'
import type { Service, ServiceStatus } from '../types.ts'

// Подписки: на какие сервисы присылать мне оповещения о сбоях.
// Сверху — как система выбирает, кому писать; ниже — список сервисов с кнопкой подписки.
export default function SubscriptionsPage() {
  const { me } = useAuth()
  const catalog = useCatalog()
  const queryClient = useQueryClient()
  const { message } = App.useApp()
  const canSubscribe = me?.role === 'engineer' || me?.role === 'manager'

  const subscriptions = useQuery({
    queryKey: ['subscriptions'],
    queryFn: fetchSubscriptions,
    enabled: canSubscribe,
  })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
  const add = useMutation({
    mutationFn: subscribe,
    onSuccess: () => {
      message.success('Вы подписаны')
      refresh()
    },
    onError: (error) => message.error(error.message),
  })
  const remove = useMutation({
    mutationFn: unsubscribe,
    onSuccess: () => {
      message.success('Подписка отменена')
      refresh()
    },
    onError: (error) => message.error(error.message),
  })

  // По диаграмме вариантов использования подписки есть у инженера и руководителя
  if (!canSubscribe) {
    return <Result status="info" title="Подписки есть у инженеров и руководителей" />
  }

  const byService = new Map((subscriptions.data ?? []).map((item) => [item.service_id, item]))

  const columns: TableProps<Service>['columns'] = [
    {
      title: 'Сервис',
      dataIndex: 'name',
      render: (name: string, service) => (
        <>
          <div style={{ fontWeight: 500 }}>{name}</div>
          <div className="hint">{service.description}</div>
        </>
      ),
    },
    {
      title: 'Состояние',
      dataIndex: 'status',
      render: (status: ServiceStatus) => <ServiceStatusTag status={status} />,
    },
    {
      title: 'Ответственный',
      dataIndex: 'owner_id',
      render: (id: number) => catalog.peopleById.get(id)?.full_name,
    },
    {
      title: 'Оповещения мне',
      key: 'subscription',
      render: (_, service) => {
        if (service.owner_id === me?.person_id) {
          return <Tag color="blue">Вы ответственный — приходят всегда</Tag>
        }
        const subscription = byService.get(service.id)
        return subscription ? (
          <Space>
            <Tag color="green">Подписаны</Tag>
            <Button size="small" loading={remove.isPending} onClick={() => remove.mutate(subscription.id)}>
              Отписаться
            </Button>
          </Space>
        ) : (
          <Button size="small" type="primary" loading={add.isPending} onClick={() => add.mutate(service.id)}>
            Подписаться
          </Button>
        )
      },
    },
  ]

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <h1>Подписки</h1>
        <p className="hint">
          Подпишитесь на сервис, чтобы получать оповещения о его сбоях, даже если вы за него не отвечаете.
        </p>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Кто получает оповещение" style={{ height: '100%' }}>
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>
                Ответственный за ресурс, с которого начался сбой (первопричину), — <b>«устранить»</b>
              </li>
              <li>
                Ответственные за затронутые сервисы и подписчики этих сервисов — <b>«к сведению»</b>
              </li>
            </ol>
            <p className="hint" style={{ margin: '8px 0 0' }}>
              Если человек попал в несколько групп, он получит одно сообщение.
            </p>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Куда" style={{ height: '100%' }}>
            На рабочую почту, а если подключён корпоративный мессенджер Mattermost — ещё и туда. Если отправка не
            удалась, система повторяет её до 3 раз с интервалом в минуту.
          </Card>
        </Col>
      </Row>

      <Card title="Сервисы">
        <Table<Service>
          rowKey="id"
          columns={columns}
          dataSource={catalog.services}
          loading={catalog.isPending || subscriptions.isPending}
          pagination={false}
        />
      </Card>
    </Space>
  )
}
