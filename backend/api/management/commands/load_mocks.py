from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from api.models import (
    Department, Person, Service, Resource,
    Incident, IncidentHistoryItem, MonitoringEvent,
)


class Command(BaseCommand):
    help = 'Загружает тестовые данные из mocks/data.ts в базу'

    def handle(self, *args, **options):
        self.stdout.write('Загружаю данные…')

        # --- Отделы ---
        departments_data = [
            (1, 'ИТ-инфраструктура'),
            (2, 'Разработка'),
            (3, 'Бухгалтерия'),
            (4, 'Отдел продаж'),
            (5, 'Служба поддержки'),
        ]
        deps = {}
        for pk, name in departments_data:
            deps[pk], _ = Department.objects.update_or_create(id=pk, defaults={'name': name})

        # --- Сотрудники ---
        people_data = [
            (1, 'Иванов Сергей', 1, 'ivanov@example.local', '@ivanov'),
            (2, 'Петрова Мария', 1, 'petrova@example.local', '@petrova'),
            (3, 'Смирнов Алексей', 2, 'smirnov@example.local', '@smirnov'),
            (4, 'Орлова Елена', 2, 'orlova@example.local', '@orlova'),
        ]
        people = {}
        for pk, full_name, dep_id, email, mm in people_data:
            people[pk], _ = Person.objects.update_or_create(
                id=pk,
                defaults=dict(
                    full_name=full_name,
                    department=deps[dep_id],
                    email=email,
                    mattermost=mm,
                ),
            )

        # --- Сервисы ---
        services_data = [
            (1, 'Корпоративный сайт', 'Сайт компании и форма заявок', 4, 3, 'ok', 99.5, 99.92),
            (2, 'CRM', 'Учёт клиентов и сделок', 4, 4, 'down', 99.9, 98.7),
            (3, 'Личный кабинет клиента', 'Заявки и статусы для клиентов', 5, 3, 'degraded', 99.5, 99.1),
            (4, '1С: Бухгалтерия', 'Бухгалтерский учёт', 3, 1, 'ok', 99.0, 99.6),
            (5, 'Корпоративная почта', 'Почта сотрудников', 1, 2, 'degraded', 99.5, 99.7),
            (6, 'Файловое хранилище', 'Общие папки и резервные копии', 1, 2, 'ok', 99.0, 100.0),
        ]
        services = {}
        for pk, name, desc, dep_id, owner_id, status, slo, avail in services_data:
            services[pk], _ = Service.objects.update_or_create(
                id=pk,
                defaults=dict(
                    name=name, description=desc,
                    department=deps[dep_id], owner=people[owner_id],
                    status=status, slo_target=slo, availability=avail,
                ),
            )

        # --- Ресурсы ---
        wiki = 'https://wiki.example.local/runbooks'
        resources_data = [
            (1, 'sw-core-01', 'network', 'prod', 'Центральный коммутатор', 1, [], [], f'{wiki}/switch'),
            (2, 'lb-01', 'application', 'prod', 'Балансировщик Nginx', 1, [1, 3], [1], f'{wiki}/nginx'),
            (3, 'web-01', 'server', 'prod', 'Веб-сервер сайта', 1, [1], [1], f'{wiki}/linux-server'),
            (4, 'app-site', 'application', 'prod', 'Приложение сайта', 3, [1], [3, 7], f'{wiki}/site'),
            (5, 'app-crm', 'application', 'prod', 'Приложение CRM', 4, [2], [8, 9], f'{wiki}/crm'),
            (6, 'app-lk', 'application', 'prod', 'Приложение личного кабинета', 3, [3], [2, 8, 10], f'{wiki}/lk'),
            (7, 'db-01', 'database', 'prod', 'PostgreSQL сайта', 1, [1], [1], f'{wiki}/postgresql'),
            (8, 'db-02', 'database', 'prod', 'PostgreSQL CRM и личного кабинета', 1, [2, 3], [1], f'{wiki}/postgresql'),
            (9, 'mq-01', 'queue', 'prod', 'RabbitMQ для CRM', 1, [2], [1], f'{wiki}/rabbitmq'),
            (10, 'redis-01', 'cache', 'prod', 'Redis личного кабинета', 1, [3], [1], f'{wiki}/redis'),
            (11, 'srv-1c', 'server', 'prod', 'Сервер 1С', 1, [4], [1, 12], f'{wiki}/1c'),
            (12, 'db-1c', 'database', 'prod', 'PostgreSQL для 1С', 1, [4], [1], f'{wiki}/postgresql'),
            (13, 'mail-01', 'server', 'prod', 'Почтовый сервер', 2, [5], [1], f'{wiki}/mail'),
            (14, 'nas-01', 'server', 'prod', 'Сетевое хранилище', 2, [6], [1], f'{wiki}/nas'),
            (15, 'backup-01', 'server', 'prod', 'Сервер резервных копий', 2, [6], [1, 14], f'{wiki}/backup'),
            (16, 'db-02-test', 'database', 'test', 'Тестовая копия базы CRM', 4, [2], [], f'{wiki}/postgresql'),
        ]
        resources = {}
        for pk, name, rtype, env, desc, owner_id, svc_ids, depends_on_ids, runbook in resources_data:
            res, _ = Resource.objects.update_or_create(
                id=pk,
                defaults=dict(
                    name=name, type=rtype, environment=env, description=desc,
                    owner=people[owner_id], runbook_url=runbook,
                ),
            )
            res.services.set([services[i] for i in svc_ids])
            resources[pk] = res

        # Второй проход: depends_on (нужны все ресурсы созданными)
        for pk, _, _, _, _, _, _, depends_on_ids, _ in resources_data:
            resources[pk].depends_on.set([resources[i] for i in depends_on_ids])

        # --- Инциденты ---
        incidents_data = [
            {
                'id': 1,
                'title': 'Недоступны CRM и личный кабинет',
                'status': 'open', 'severity': 'critical',
                'root_cause_id': 8, 'affected_service_ids': [2, 3],
                'responsible_id': 1,
                'started_at': '2026-10-22T09:14:05+07:00',
                'resolved_at': None,
                'history': [
                    ('2026-10-22T09:14:05+07:00', 'Инцидент создан по событию от Zabbix'),
                    ('2026-10-22T09:14:40+07:00', 'Добавлены события-следствия: app-crm, app-lk'),
                    ('2026-10-22T09:14:42+07:00', 'Оповещены: Иванов Сергей (Mattermost), Орлова Елена (почта)'),
                ],
            },
            {
                'id': 2,
                'title': 'Заканчивается место на почтовом сервере',
                'status': 'in_progress', 'severity': 'warning',
                'root_cause_id': 13, 'affected_service_ids': [5],
                'responsible_id': 2,
                'started_at': '2026-10-22T07:40:00+07:00',
                'resolved_at': None,
                'history': [
                    ('2026-10-22T07:40:00+07:00', 'Инцидент создан по событию от Zabbix'),
                    ('2026-10-22T07:40:02+07:00', 'Оповещена: Петрова Мария (Mattermost)'),
                    ('2026-10-22T08:05:00+07:00', 'Петрова Мария взяла в работу'),
                ],
            },
            {
                'id': 3,
                'title': 'Сбой центрального коммутатора',
                'status': 'resolved', 'severity': 'critical',
                'root_cause_id': 1, 'affected_service_ids': [1, 2, 3, 4, 5, 6],
                'responsible_id': 1,
                'started_at': '2026-10-20T13:02:10+07:00',
                'resolved_at': '2026-10-20T13:27:00+07:00',
                'history': [
                    ('2026-10-20T13:02:10+07:00', 'Инцидент создан по событию от Zabbix'),
                    ('2026-10-20T13:03:20+07:00', '4 события распознаны как следствия и добавлены в инцидент'),
                    ('2026-10-20T13:03:22+07:00', 'Оповещены: Иванов Сергей (Mattermost)'),
                    ('2026-10-20T13:06:00+07:00', 'Иванов Сергей взял в работу'),
                    ('2026-10-20T13:27:00+07:00', 'Закрыт: заменён блок питания коммутатора'),
                ],
            },
            {
                'id': 4,
                'title': 'Высокая загрузка процессора на сервере 1С',
                'status': 'resolved', 'severity': 'warning',
                'root_cause_id': 11, 'affected_service_ids': [4],
                'responsible_id': 1,
                'started_at': '2026-10-19T10:15:00+07:00',
                'resolved_at': '2026-10-19T10:50:00+07:00',
                'history': [
                    ('2026-10-19T10:15:00+07:00', 'Инцидент создан по событию от Zabbix'),
                    ('2026-10-19T10:20:00+07:00', 'Иванов Сергей взял в работу'),
                    ('2026-10-19T10:50:00+07:00', 'Закрыт: завершён зависший фоновый отчёт'),
                ],
            },
        ]
        incidents = {}
        for data in incidents_data:
            inc, _ = Incident.objects.update_or_create(
                id=data['id'],
                defaults=dict(
                    title=data['title'], status=data['status'], severity=data['severity'],
                    root_cause=resources[data['root_cause_id']],
                    responsible=people[data['responsible_id']],
                    started_at=parse_datetime(data['started_at']),
                    resolved_at=parse_datetime(data['resolved_at']) if data['resolved_at'] else None,
                ),
            )
            inc.affected_services.set([services[i] for i in data['affected_service_ids']])
            inc.history.all().delete()
            for at, text in data['history']:
                IncidentHistoryItem.objects.create(
                    incident=inc, at=parse_datetime(at), text=text,
                )
            incidents[data['id']] = inc

        # --- События ---
        events_data = [
            (1, 1, 'zabbix', 8, 'PostgreSQL: нет ответа на порту 5432', 'critical', '2026-10-22T09:14:05+07:00'),
            (2, 1, 'prometheus', 5, 'Доля ошибок 5xx выше 20%', 'critical', '2026-10-22T09:14:40+07:00'),
            (3, 1, 'prometheus', 6, 'Время ответа выше 3 секунд', 'warning', '2026-10-22T09:15:10+07:00'),
            (4, 1, 'zabbix', 5, 'Веб-проверка CRM не проходит', 'critical', '2026-10-22T09:15:30+07:00'),
            (5, 2, 'zabbix', 13, 'Свободно меньше 10% на /var', 'warning', '2026-10-22T07:40:00+07:00'),
            (6, 3, 'zabbix', 1, 'Нет ответа на ping', 'critical', '2026-10-20T13:02:10+07:00'),
            (7, 3, 'prometheus', 2, 'HTTP-проверка не проходит', 'critical', '2026-10-20T13:02:40+07:00'),
            (8, 3, 'zabbix', 13, 'Нет ответа на ping', 'critical', '2026-10-20T13:02:45+07:00'),
            (9, 3, 'zabbix', 11, 'Нет ответа на ping', 'critical', '2026-10-20T13:03:00+07:00'),
            (10, 3, 'prometheus', 5, 'Цель мониторинга недоступна', 'critical', '2026-10-20T13:03:20+07:00'),
            (11, 4, 'zabbix', 11, 'Загрузка процессора выше 90% дольше 10 минут', 'warning', '2026-10-19T10:15:00+07:00'),
        ]
        for pk, inc_id, source, res_id, title, severity, received_at in events_data:
            MonitoringEvent.objects.update_or_create(
                id=pk,
                defaults=dict(
                    incident=incidents[inc_id], source=source,
                    resource=resources[res_id], title=title,
                    severity=severity, received_at=parse_datetime(received_at),
                ),
            )

        self.stdout.write(self.style.SUCCESS(
            f'Готово: отделов {Department.objects.count()}, '
            f'сотрудников {Person.objects.count()}, '
            f'сервисов {Service.objects.count()}, '
            f'ресурсов {Resource.objects.count()}, '
            f'инцидентов {Incident.objects.count()}, '
            f'событий {MonitoringEvent.objects.count()}.'
        ))