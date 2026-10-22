import { Card, Col, Row, Space, Table, Tag } from 'antd'
import type { TableProps } from 'antd'
import { SeverityTag } from '../components/StatusTags.tsx'
import type { Severity } from '../types.ts'

// Страница пока описывает, как будет работать рассылка оповещений.
// Хранение подписок и само правило отправки появятся вместе с бэкендом.

type Example = {
  key: number
  time: string
  what: string
  severity: Severity
  who: string
  when: string
}

const examples: Example[] = [
  { key: 1, time: '09:14', what: 'Упала db-02, не работает CRM', severity: 'critical', who: 'Иванов С. (Mattermost), Орлова Е. (почта)', when: 'сразу' },
  { key: 2, time: '07:40', what: 'На mail-01 заканчивается место', severity: 'warning', who: 'Петрова М. (Mattermost)', when: 'сразу (уже утро)' },
  { key: 3, time: '03:20', what: 'На mail-01 заканчивается место', severity: 'warning', who: 'Петрова М. (Mattermost)', when: 'в 08:00, в сводке' },
  { key: 4, time: '03:20', what: 'Упал sw-core-01, не работает всё', severity: 'critical', who: 'Иванов С. (Mattermost)', when: 'сразу, ночью' },
]

const columns: TableProps<Example>['columns'] = [
  { title: 'Когда', dataIndex: 'time', width: 80 },
  { title: 'Что случилось', dataIndex: 'what' },
  { title: 'Важность', dataIndex: 'severity', render: (severity: Severity) => <SeverityTag severity={severity} /> },
  { title: 'Кто получит', dataIndex: 'who' },
  { title: 'Когда получит', dataIndex: 'when' },
]

export default function SubscriptionsPage() {
  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <h1>
          Подписки <Tag>в разработке</Tag>
        </h1>
        <p className="hint">Как система решает, кому и когда отправить оповещение о сбое.</p>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="Кто получает" style={{ height: '100%' }}>
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              <li>Ответственный за сервис, указанный в каталоге</li>
              <li>Сотрудники, подписанные на этот сервис</li>
            </ol>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Куда" style={{ height: '100%' }}>
            Mattermost или почта — каждый выбирает сам.
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Ночью (22:00–08:00)" style={{ height: '100%' }}>
            <Space orientation="vertical">
              <span>
                <SeverityTag severity="critical" /> — приходят сразу
              </span>
              <span>
                <SeverityTag severity="warning" /> — откладываются до 08:00 и приходят одной сводкой
              </span>
            </Space>
          </Card>
        </Col>
      </Row>

      <Card title="Примеры на тестовых данных">
        <Table<Example> columns={columns} dataSource={examples} pagination={false} size="small" />
      </Card>
    </Space>
  )
}
