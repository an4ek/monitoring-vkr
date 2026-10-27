// Тестовые данные: небольшая организация с шестью ИТ-сервисами.
// Пока бэкенда нет, страницы берут данные отсюда.
// Потом те же данные будут в базе, а здесь останутся только для проверки интерфейса.
import type {
  Department,
  Incident,
  MonitoringEvent,
  Person,
  Resource,
  Service,
} from '../types.ts'

export const departments: Department[] = [
  { id: 1, name: 'ИТ-инфраструктура' },
  { id: 2, name: 'Разработка' },
  { id: 3, name: 'Бухгалтерия' },
  { id: 4, name: 'Отдел продаж' },
  { id: 5, name: 'Служба поддержки' },
]

export const people: Person[] = [
  { id: 1, full_name: 'Иванов Сергей', department_id: 1, email: 'ivanov@example.local', mattermost: '@ivanov' },
  { id: 2, full_name: 'Петрова Мария', department_id: 1, email: 'petrova@example.local', mattermost: '@petrova' },
  { id: 3, full_name: 'Смирнов Алексей', department_id: 2, email: 'smirnov@example.local', mattermost: '@smirnov' },
  { id: 4, full_name: 'Орлова Елена', department_id: 2, email: 'orlova@example.local', mattermost: '@orlova' },
]

export const services: Service[] = [
  { id: 1, name: 'Корпоративный сайт', description: 'Сайт компании и форма заявок', department_id: 4, owner_id: 3, status: 'ok', slo_target: 99.5, availability: 99.92 },
  { id: 2, name: 'CRM', description: 'Учёт клиентов и сделок', department_id: 4, owner_id: 4, status: 'down', slo_target: 99.9, availability: 98.7 },
  { id: 3, name: 'Личный кабинет клиента', description: 'Заявки и статусы для клиентов', department_id: 5, owner_id: 3, status: 'degraded', slo_target: 99.5, availability: 99.1 },
  { id: 4, name: '1С: Бухгалтерия', description: 'Бухгалтерский учёт', department_id: 3, owner_id: 1, status: 'ok', slo_target: 99.0, availability: 99.6 },
  { id: 5, name: 'Корпоративная почта', description: 'Почта сотрудников', department_id: 1, owner_id: 2, status: 'degraded', slo_target: 99.5, availability: 99.7 },
  { id: 6, name: 'Файловое хранилище', description: 'Общие папки и резервные копии', department_id: 1, owner_id: 2, status: 'ok', slo_target: 99.0, availability: 100 },
]

const wiki = 'https://wiki.example.local/runbooks'

export const resources: Resource[] = [
  { id: 1, name: 'sw-core-01', type: 'network', environment: 'prod', description: 'Центральный коммутатор', owner_id: 1, service_ids: [], depends_on: [], runbook_url: `${wiki}/switch` },
  { id: 2, name: 'lb-01', type: 'application', environment: 'prod', description: 'Балансировщик Nginx', owner_id: 1, service_ids: [1, 3], depends_on: [1], runbook_url: `${wiki}/nginx` },
  { id: 3, name: 'web-01', type: 'server', environment: 'prod', description: 'Веб-сервер сайта', owner_id: 1, service_ids: [1], depends_on: [1], runbook_url: `${wiki}/linux-server` },
  { id: 4, name: 'app-site', type: 'application', environment: 'prod', description: 'Приложение сайта', owner_id: 3, service_ids: [1], depends_on: [3, 7], runbook_url: `${wiki}/site` },
  { id: 5, name: 'app-crm', type: 'application', environment: 'prod', description: 'Приложение CRM', owner_id: 4, service_ids: [2], depends_on: [8, 9], runbook_url: `${wiki}/crm` },
  { id: 6, name: 'app-lk', type: 'application', environment: 'prod', description: 'Приложение личного кабинета', owner_id: 3, service_ids: [3], depends_on: [2, 8, 10], runbook_url: `${wiki}/lk` },
  { id: 7, name: 'db-01', type: 'database', environment: 'prod', description: 'PostgreSQL сайта', owner_id: 1, service_ids: [1], depends_on: [1], runbook_url: `${wiki}/postgresql` },
  { id: 8, name: 'db-02', type: 'database', environment: 'prod', description: 'PostgreSQL CRM и личного кабинета', owner_id: 1, service_ids: [2, 3], depends_on: [1], runbook_url: `${wiki}/postgresql` },
  { id: 9, name: 'mq-01', type: 'queue', environment: 'prod', description: 'RabbitMQ для CRM', owner_id: 1, service_ids: [2], depends_on: [1], runbook_url: `${wiki}/rabbitmq` },
  { id: 10, name: 'redis-01', type: 'cache', environment: 'prod', description: 'Redis личного кабинета', owner_id: 1, service_ids: [3], depends_on: [1], runbook_url: `${wiki}/redis` },
  { id: 11, name: 'srv-1c', type: 'server', environment: 'prod', description: 'Сервер 1С', owner_id: 1, service_ids: [4], depends_on: [1, 12], runbook_url: `${wiki}/1c` },
  { id: 12, name: 'db-1c', type: 'database', environment: 'prod', description: 'PostgreSQL для 1С', owner_id: 1, service_ids: [4], depends_on: [1], runbook_url: `${wiki}/postgresql` },
  { id: 13, name: 'mail-01', type: 'server', environment: 'prod', description: 'Почтовый сервер', owner_id: 2, service_ids: [5], depends_on: [1], runbook_url: `${wiki}/mail` },
  { id: 14, name: 'nas-01', type: 'server', environment: 'prod', description: 'Сетевое хранилище', owner_id: 2, service_ids: [6], depends_on: [1], runbook_url: `${wiki}/nas` },
  { id: 15, name: 'backup-01', type: 'server', environment: 'prod', description: 'Сервер резервных копий', owner_id: 2, service_ids: [6], depends_on: [1, 14], runbook_url: `${wiki}/backup` },
  { id: 16, name: 'db-02-test', type: 'database', environment: 'test', description: 'Тестовая копия базы CRM', owner_id: 4, service_ids: [2], depends_on: [], runbook_url: `${wiki}/postgresql` },
]

export const incidents: Incident[] = [
  {
    id: 1,
    title: 'Недоступны CRM и личный кабинет',
    status: 'open',
    severity: 'critical',
    root_cause_id: 8,
    affected_service_ids: [2, 3],
    responsible_id: 1,
    assignee_id: null,
    closed_by_id: null,
    started_at: '2026-10-22T09:14:05+07:00',
    resolved_at: null,
    history: [
      { at: '2026-10-22T09:14:05+07:00', text: 'Инцидент создан по событию от Zabbix' },
      { at: '2026-10-22T09:14:40+07:00', text: 'Добавлены события-следствия: app-crm, app-lk' },
      { at: '2026-10-22T09:14:42+07:00', text: 'Оповещены: Иванов Сергей (Mattermost), Орлова Елена (почта)' },
    ],
  },
  {
    id: 2,
    title: 'Заканчивается место на почтовом сервере',
    status: 'in_progress',
    severity: 'warning',
    root_cause_id: 13,
    affected_service_ids: [5],
    responsible_id: 2,
    assignee_id: 2,
    closed_by_id: null,
    started_at: '2026-10-22T07:40:00+07:00',
    resolved_at: null,
    history: [
      { at: '2026-10-22T07:40:00+07:00', text: 'Инцидент создан по событию от Zabbix' },
      { at: '2026-10-22T07:40:02+07:00', text: 'Оповещена: Петрова Мария (Mattermost)' },
      { at: '2026-10-22T08:05:00+07:00', text: 'Петрова Мария взяла в работу' },
    ],
  },
  {
    id: 3,
    title: 'Сбой центрального коммутатора',
    status: 'resolved',
    severity: 'critical',
    root_cause_id: 1,
    affected_service_ids: [1, 2, 3, 4, 5, 6],
    responsible_id: 1,
    assignee_id: 1,
    closed_by_id: 1,
    started_at: '2026-10-20T13:02:10+07:00',
    resolved_at: '2026-10-20T13:27:00+07:00',
    history: [
      { at: '2026-10-20T13:02:10+07:00', text: 'Инцидент создан по событию от Zabbix' },
      { at: '2026-10-20T13:03:20+07:00', text: '4 события распознаны как следствия и добавлены в инцидент' },
      { at: '2026-10-20T13:03:22+07:00', text: 'Оповещены: Иванов Сергей (Mattermost)' },
      { at: '2026-10-20T13:06:00+07:00', text: 'Иванов Сергей взял в работу' },
      { at: '2026-10-20T13:27:00+07:00', text: 'Закрыт: заменён блок питания коммутатора' },
    ],
  },
  {
    id: 4,
    title: 'Высокая загрузка процессора на сервере 1С',
    status: 'resolved',
    severity: 'warning',
    root_cause_id: 11,
    affected_service_ids: [4],
    responsible_id: 1,
    assignee_id: 1,
    closed_by_id: 1,
    started_at: '2026-10-19T10:15:00+07:00',
    resolved_at: '2026-10-19T10:50:00+07:00',
    history: [
      { at: '2026-10-19T10:15:00+07:00', text: 'Инцидент создан по событию от Zabbix' },
      { at: '2026-10-19T10:20:00+07:00', text: 'Иванов Сергей взял в работу' },
      { at: '2026-10-19T10:50:00+07:00', text: 'Закрыт: завершён зависший фоновый отчёт' },
    ],
  },
]

export const events: MonitoringEvent[] = [
  { id: 1, incident_id: 1, source: 'zabbix', resource_id: 8, title: 'PostgreSQL: нет ответа на порту 5432', severity: 'critical', received_at: '2026-10-22T09:14:05+07:00' },
  { id: 2, incident_id: 1, source: 'prometheus', resource_id: 5, title: 'Доля ошибок 5xx выше 20%', severity: 'critical', received_at: '2026-10-22T09:14:40+07:00' },
  { id: 3, incident_id: 1, source: 'prometheus', resource_id: 6, title: 'Время ответа выше 3 секунд', severity: 'warning', received_at: '2026-10-22T09:15:10+07:00' },
  { id: 4, incident_id: 1, source: 'zabbix', resource_id: 5, title: 'Веб-проверка CRM не проходит', severity: 'critical', received_at: '2026-10-22T09:15:30+07:00' },
  { id: 5, incident_id: 2, source: 'zabbix', resource_id: 13, title: 'Свободно меньше 10% на /var', severity: 'warning', received_at: '2026-10-22T07:40:00+07:00' },
  { id: 6, incident_id: 3, source: 'zabbix', resource_id: 1, title: 'Нет ответа на ping', severity: 'critical', received_at: '2026-10-20T13:02:10+07:00' },
  { id: 7, incident_id: 3, source: 'prometheus', resource_id: 2, title: 'HTTP-проверка не проходит', severity: 'critical', received_at: '2026-10-20T13:02:40+07:00' },
  { id: 8, incident_id: 3, source: 'zabbix', resource_id: 13, title: 'Нет ответа на ping', severity: 'critical', received_at: '2026-10-20T13:02:45+07:00' },
  { id: 9, incident_id: 3, source: 'zabbix', resource_id: 11, title: 'Нет ответа на ping', severity: 'critical', received_at: '2026-10-20T13:03:00+07:00' },
  { id: 10, incident_id: 3, source: 'prometheus', resource_id: 5, title: 'Цель мониторинга недоступна', severity: 'critical', received_at: '2026-10-20T13:03:20+07:00' },
  { id: 11, incident_id: 4, source: 'zabbix', resource_id: 11, title: 'Загрузка процессора выше 90% дольше 10 минут', severity: 'warning', received_at: '2026-10-19T10:15:00+07:00' },
]
