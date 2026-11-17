"""Проверки обработки событий. Запуск: python manage.py test processing

Обработка идет триггером в базе (миграция processing/0005). Те же сценарии
прогоняются и через эталон на Python (processing/logic.py) с выключенным триггером,
а EquivalenceTests сравнивает, что оба пути дают одинаковые данные.
"""
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from api.models import (
    BusinessService, Event, Incident, IncidentService, IncidentTimeline, MonitoringSystem,
    Notification, ResourceState, Subscription,
)
from processing import logic
from processing.models import IncomingEvent
from processing.normalize import from_alertmanager, from_zabbix
from processing.tasks import send_notifications

RESULT_BY_STATUS = {
    IncomingEvent.Status.ATTACHED: 'attached',
    IncomingEvent.Status.RECOVERED: 'recovery',
    IncomingEvent.Status.UNKNOWN_RESOURCE: 'unknown_resource',
    IncomingEvent.Status.FAILED: 'failed',
}


def zabbix(event_id, host, kind='problem', severity='critical', title='Нет ответа на ping', source='zabbix'):
    return {'source': source, 'external_id': str(event_id), 'kind': kind,
            'resource_name': host, 'title': title, 'severity': severity}

def feed(event_id, host, **kwargs):
    """Как будто view уже записал событие в IncomingEvent. Возвращает запись."""
    event = zabbix(event_id, host, **kwargs)
    return IncomingEvent.objects.create(**event, payload=event)

def reset_demo_data():
    with mock.patch('sys.stdout'):
        call_command('demo_reset')

def set_trigger(enabled):
    """Выключатель триггера на текущую транзакцию — только для пути через эталон на Python."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('processing.trigger_off', %s, true)", ['off' if enabled else 'on'])

def db_process_again(incoming):
    """Повторный запуск обработки в базе для уже обработанного события."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT processing_process_event(%s)', [incoming.id])
        return cursor.fetchone()[0]


class ScenarioMixin:
    """Сценарии обработки. Подкласс задает, кто обрабатывает: эталон на Python или база."""

    def handle(self, event_id, host, **kwargs):
        """Принять и обработать событие. Возвращает (результат, id инцидента)."""
        raise NotImplementedError

    def handle_again(self, incoming):
        """Еще раз обработать уже принятое событие (как будто статус не записался)."""
        raise NotImplementedError

    def test_reprocessing_does_not_duplicate(self):
        incidents_before = Incident.objects.count()  # demo_reset уже создает тестовый инцидент
        _, incident_id = self.handle(1, 'web-01')
        self.handle_again(IncomingEvent.objects.get(external_id='1'))
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Incident.objects.count(), incidents_before + 1)
        self.assertEqual(IncidentTimeline.objects.filter(incident_id=incident_id).count(), 1)

    def test_duplicate_is_ignored(self):
        self.assertEqual(self.handle(1, 'web-01')[0], 'attached')
        # Повтор того же события не записывается второй раз: его отсекает уникальность
        with self.assertRaises(IntegrityError), transaction.atomic():
            feed(1, 'web-01')
        self.assertEqual(IncomingEvent.objects.count(), 1)
        self.assertEqual(Event.objects.count(), 1)

    def test_unknown_resource_is_saved(self):
        self.assertEqual(self.handle(1, 'no-such-host')[0], 'unknown_resource')
        self.assertEqual(IncomingEvent.objects.get().status, IncomingEvent.Status.UNKNOWN_RESOURCE)
        self.assertEqual(Event.objects.count(), 0)

    def test_grouping_and_root_cause(self):
        _, first = self.handle(1, 'web-01')
        _, second = self.handle(2, 'db-01')
        self.assertEqual(first, second)  # одна авария — один инцидент
        self.assertEqual(Incident.objects.get(id=first).root_cause_ci.name, 'web-01')

        _, third = self.handle(3, 'sw-core-01')
        incident = Incident.objects.get(id=third)
        self.assertEqual(third, first)
        self.assertEqual(incident.root_cause_ci.name, 'sw-core-01')  # коммутатор, от которого зависят оба
        self.assertEqual(incident.title, 'Сбой: Центральный коммутатор (sw-core-01)')
        self.assertTrue(IncidentTimeline.objects.filter(
            incident=incident, text='Первопричина изменена: web-01 → sw-core-01').exists())
        self.assertEqual(BusinessService.objects.get(name='Корпоративный сайт').current_status, 'down')

    def test_recovery_closes_incident(self):
        _, incident_id = self.handle(1, 'web-01')
        self.handle(2, 'sw-core-01')
        self.assertEqual(self.handle(2, 'sw-core-01', kind='recovery')[0], 'recovery')
        incident = Incident.objects.get(id=incident_id)
        self.assertEqual(incident.status, 'open')  # web-01 еще в сбое
        self.assertEqual(incident.root_cause_ci.name, 'sw-core-01')  # первопричина не меняется при починке
        self.handle(1, 'web-01', kind='recovery')
        incident.refresh_from_db()
        self.assertEqual(incident.status, 'resolved')
        self.assertIsNotNone(incident.resolved_at)
        self.assertFalse(ResourceState.objects.get(resource__name='web-01').is_failing)
        self.assertEqual(BusinessService.objects.get(name='Корпоративный сайт').current_status, 'ok')

    def test_recovery_reprocessing_does_not_duplicate(self):
        _, incident_id = self.handle(1, 'web-01')
        self.handle(2, 'db-01')  # тот же инцидент, web-01 остается в сбое
        self.handle(2, 'db-01', kind='recovery')
        events = Event.objects.count()
        history = IncidentTimeline.objects.filter(incident_id=incident_id).count()

        self.handle_again(IncomingEvent.objects.get(external_id='2', kind='recovery'))
        self.assertEqual(Event.objects.count(), events)
        self.assertEqual(IncidentTimeline.objects.filter(incident_id=incident_id).count(), history)
        self.assertEqual(Incident.objects.get(id=incident_id).status, 'open')


# Быстрый хеш паролей только для проверок, чтобы тесты не шли минуту
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PythonProcessingTests(ScenarioMixin, TestCase):
    """Сценарии через эталон processing/logic.py; триггер выключен на время теста."""

    def setUp(self):
        reset_demo_data()
        set_trigger(False)

    def handle(self, event_id, host, **kwargs):
        result, incident_id, _ = logic.process(feed(event_id, host, **kwargs))
        return result, incident_id

    def handle_again(self, incoming):
        logic.process(incoming)

    def test_notification_decision(self):
        """Решение о рассылке есть только в эталоне: в базе рассылки пока нет."""
        notify1 = logic.process(feed(1, 'web-01'))[2]
        notify2 = logic.process(feed(2, 'db-01'))[2]
        notify3 = logic.process(feed(3, 'sw-core-01'))[2]
        self.assertTrue(notify1)
        self.assertFalse(notify2)  # первопричина и сервисы те же
        self.assertTrue(notify3)  # первопричина изменилась — повторная рассылка


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DbProcessingTests(ScenarioMixin, TestCase):
    """Те же сценарии через триггер в базе."""

    def setUp(self):
        reset_demo_data()

    def handle(self, event_id, host, **kwargs):
        incoming = feed(event_id, host, **kwargs)  # обработку запускает триггер
        incoming.refresh_from_db()
        result = RESULT_BY_STATUS.get(incoming.status, incoming.status)
        event = Event.objects.filter(fingerprint=incoming.external_id[:64], status='firing').first()
        incident_id = event.incident_id if result == 'attached' and event else None
        return result, incident_id

    def handle_again(self, incoming):
        db_process_again(incoming)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TriggerTests(TestCase):
    """Поведение, которого нет в эталоне: статус, попытки, ошибки, настройки."""

    def setUp(self):
        reset_demo_data()

    def test_status_and_time_are_set(self):
        incoming = feed(1, 'web-01')
        incoming.refresh_from_db()
        self.assertEqual((incoming.status, incoming.attempts, incoming.error),
                         (IncomingEvent.Status.ATTACHED, 1, ''))
        self.assertIsNotNone(incoming.processed_at)

    def test_failure_rolls_back_processing_and_keeps_event(self):
        incidents = Incident.objects.count()
        history = IncidentTimeline.objects.count()
        # Важность длиннее поля инцидента: ошибка после того, как состояние ресурса уже записано
        incoming = feed(1, 'web-01', severity='x' * 15)
        incoming.refresh_from_db()
        self.assertEqual((incoming.status, incoming.attempts), (IncomingEvent.Status.FAILED, 1))
        self.assertIn('value too long', incoming.error)
        self.assertIsNone(incoming.processed_at)
        # Изменения по инциденту откатились, само событие осталось
        self.assertEqual(Incident.objects.count(), incidents)
        self.assertEqual(IncidentTimeline.objects.count(), history)
        self.assertEqual(Event.objects.count(), 0)
        self.assertFalse(ResourceState.objects.filter(resource__name='web-01', is_failing=True).exists())
        # Блокировка склейки взята до блока EXCEPTION и держится до конца транзакции
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid() "
                "AND objid = %s AND granted", [logic.GROUPING_LOCK_ID])
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_group_window_setting(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('processing.group_window_minutes', '0', true)")
        feed(1, 'web-01')
        feed(2, 'db-01')  # окно 0 минут: свежих событий нет, инцидент новый
        incidents = set(Event.objects.values_list('incident_id', flat=True))
        self.assertEqual(len(incidents), 2)

    @override_settings(MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
    def test_recipients_deduplicated(self):
        feed(1, 'web-01')
        incident_id = Event.objects.get().incident_id
        send_notifications(incident_id)
        notes = Notification.objects.filter(incident_id=incident_id)
        people = [n.person_id for n in notes]
        self.assertEqual(len(people), len(set(people)))  # каждому одно сообщение
        fix = notes.get(kind='fix')
        self.assertEqual(fix.person.full_name, 'Иванов Сергей')  # ответственный за web-01
        self.assertTrue(all(n.status == 'sent' for n in notes))

    def test_normalize(self):
        [z] = from_zabbix({'event_id': 1, 'host': 'web-01', 'name': 'x', 'severity': '5', 'status': '0'})
        self.assertEqual((z['kind'], z['severity']), ('recovery', 'critical'))
        [a] = from_alertmanager({'alerts': [{'status': 'firing', 'labels': {'instance': 'db-01:9187', 'severity': 'warning'},
                                             'annotations': {'summary': 's'}, 'fingerprint': 'f', 'startsAt': 't'}]})
        self.assertEqual((a['resource_name'], a['kind']), ('db-01', 'problem'))


# Последовательность для сравнения: склейка, смена первопричины, неизвестный ресурс,
# второй источник, восстановления, повторы, закрытие и новый инцидент после закрытия.
EQUIVALENCE_STEPS = [
    ('event', 1, 'web-01', {}),
    ('event', 2, 'db-01', {'severity': 'warning'}),
    ('again', 2, 'problem', None),
    ('event', 3, 'sw-core-01', {}),
    ('event', 4, 'no-such-host', {}),
    ('event', 5, 'mq-01', {'source': 'prometheus', 'severity': 'warning', 'title': 'Очередь растет'}),
    ('event', 6, 'mail-01', {'severity': 'info', 'title': 'Медленная доставка'}),
    ('event', 3, 'sw-core-01', {'kind': 'recovery'}),
    ('again', 3, 'recovery', None),
    ('event', 8, 'lb-01', {'kind': 'recovery'}),
    ('event', 1, 'web-01', {'kind': 'recovery'}),
    ('event', 2, 'db-01', {'kind': 'recovery'}),
    ('event', 5, 'mq-01', {'kind': 'recovery', 'source': 'prometheus', 'title': 'Очередь растет'}),
    ('event', 6, 'mail-01', {'kind': 'recovery', 'title': 'Медленная доставка'}),
    ('event', 7, 'db-02', {}),
    ('event', 9, 'db-01', {}),
]


def snapshot():
    """Данные, которые пишет обработка, без времени, случайного номера инцидента и рассылки."""
    return {
        'incidents': [
            (i.id, i.title, i.status, i.severity, i.root_cause_ci_id, i.responsible_id,
             i.events_count, i.resolution_note, i.resolved_at is None)
            for i in Incident.objects.order_by('id')
        ],
        'events': [
            (e.id, e.incident_id, e.ci_id, e.monitoring_system.name, e.fingerprint, e.title,
             e.severity, e.status, e.dedup_count, e.labels, e.raw_payload, e.resolved_at is None)
            for e in Event.objects.select_related('monitoring_system').order_by('id')
        ],
        'timeline': list(IncidentTimeline.objects.order_by('id').values_list(
            'id', 'incident_id', 'entry_type', 'text', 'actor_id')),
        'resource_states': [
            (s.resource_id, s.is_failing, s.severity, s.since is None)
            for s in ResourceState.objects.order_by('resource_id')
        ],
        'incident_services': sorted(IncidentService.objects.values_list('incident_id', 'service_id', 'impact_level')),
        'services': list(BusinessService.objects.order_by('id').values_list('id', 'current_status', 'status_updated_at')),
        'monitoring_systems': list(MonitoringSystem.objects.order_by('id').values_list(
            'id', 'name', 'system_type', 'base_url', 'ingest_method', 'webhook_secret_hash', 'is_active', 'last_event_at')),
        'incoming': sorted(
            (e.source, e.external_id, e.kind, e.status, e.error, e.processed_at is None)
            for e in IncomingEvent.objects.all()
        ),
    }


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EquivalenceTests(TestCase):
    """Эталон на Python и триггер в базе дают одинаковые данные на одной последовательности."""

    def run_steps(self, process, process_again):
        for step, event_id, host_or_kind, kwargs in EQUIVALENCE_STEPS:
            if step == 'event':
                process(feed(event_id, host_or_kind, **kwargs))
            else:
                process_again(IncomingEvent.objects.get(external_id=str(event_id), kind=host_or_kind))

    def test_python_and_database_give_same_data(self):
        reset_demo_data()
        set_trigger(False)
        self.run_steps(logic.process, logic.process)
        expected = snapshot()

        # Отложенные проверки внешних ключей мешают TRUNCATE в той же транзакции: выполняем их сразу
        with connection.cursor() as cursor:
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            reset_demo_data()  # счетчики id обнуляются, поэтому id можно сравнивать напрямую
            cursor.execute('SET CONSTRAINTS ALL DEFERRED')
        set_trigger(True)
        self.run_steps(lambda incoming: None, db_process_again)  # обработку запускает триггер
        actual = snapshot()

        self.assertGreater(len(expected['events']), 10)  # последовательность действительно что-то сделала
        for key in expected:
            self.assertEqual(actual[key], expected[key], key)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ReprocessFailedTests(TransactionTestCase):
    """CALL reprocess_failed() делает COMMIT после каждого события, поэтому нужны настоящие транзакции."""

    def setUp(self):
        reset_demo_data()

    def call_reprocess(self):
        with connection.cursor() as cursor:
            cursor.execute('CALL reprocess_failed()')
            return cursor.fetchone()[0]

    def test_failed_event_is_processed_again(self):
        incoming = feed(1, 'web-01', severity='x' * 15)
        incoming.refresh_from_db()
        self.assertEqual(incoming.status, IncomingEvent.Status.FAILED)

        IncomingEvent.objects.filter(id=incoming.id).update(severity='critical')  # причину ошибки устранили
        self.assertEqual(self.call_reprocess(), 1)
        incoming.refresh_from_db()
        self.assertEqual((incoming.status, incoming.attempts, incoming.error),
                         (IncomingEvent.Status.ATTACHED, 2, ''))
        self.assertEqual(Event.objects.get().ci.name, 'web-01')
        self.assertEqual(self.call_reprocess(), 0)  # событий со статусом «Ошибка обработки» больше нет

    def test_still_failing_event_counts_attempts(self):
        incoming = feed(1, 'web-01', severity='x' * 15)
        self.call_reprocess()
        incoming.refresh_from_db()
        self.assertEqual((incoming.status, incoming.attempts), (IncomingEvent.Status.FAILED, 2))
        self.assertEqual(Incident.objects.filter(root_cause_ci__name='web-01').count(), 0)


# Быстрый хеш паролей только для проверок, чтобы тесты не шли минуту
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AccessTests(TestCase):
    """Права: без входа ничего, мониторинг — только с ключом, разбор инцидента — только инженер."""
    def setUp(self):
        with mock.patch('sys.stdout'):
            call_command('demo_reset')

    def login(self, username):
        self.client.force_login(User.objects.get(username=username))

    def test_api_requires_login(self):
        self.assertEqual(self.client.get('/api/incidents/').status_code, 403)
        self.assertEqual(self.client.get('/api/health/').status_code, 200)
        self.login('orlova')
        self.assertEqual(self.client.get('/api/incidents/').status_code, 200)

    @mock.patch('processing.views.process_event.delay')
    def test_duplicate_is_not_queued_again(self, delay):
        body = {'event_id': 1, 'host': 'web-01', 'name': 'x', 'severity': '5', 'status': '1'}
        headers = {'X-Webhook-Token': settings.WEBHOOK_TOKEN}
        post = lambda: self.client.post('/api/events/zabbix/', body, content_type='application/json', headers=headers)
        first, second = post(), post()
        self.assertEqual((first.status_code, second.status_code), (202, 202))
        self.assertEqual(second.json()['duplicates'], 1)
        self.assertEqual(IncomingEvent.objects.count(), 1)
        # Триггер обработал событие при вставке, поэтому повтор в очередь не ставится
        self.assertEqual(IncomingEvent.objects.get().status, IncomingEvent.Status.ATTACHED)
        self.assertEqual(delay.call_count, 1)

    @mock.patch('processing.views.process_event.delay', side_effect=ConnectionError('брокер недоступен'))
    def test_event_is_saved_when_broker_is_down(self, delay):
        body = {'event_id': 7, 'host': 'web-01', 'name': 'x', 'severity': '5', 'status': '1'}
        with self.assertLogs('processing.views', 'ERROR'):  # ошибка брокера пишется в лог
            response = self.client.post('/api/events/zabbix/', body, content_type='application/json',
                                        headers={'X-Webhook-Token': settings.WEBHOOK_TOKEN})
        self.assertEqual(response.status_code, 202)
        # Брокер для обработки не нужен: триггер уже обработал событие при вставке
        self.assertEqual(IncomingEvent.objects.get().status, IncomingEvent.Status.ATTACHED)

    @mock.patch('processing.views.process_event.delay')
    def test_webhook_requires_token(self, delay):
        body = {'event_id': 1, 'host': 'web-01', 'name': 'x'}
        self.assertEqual(self.client.post('/api/events/zabbix/', body, content_type='application/json').status_code, 403)
        response = self.client.post('/api/events/zabbix/', body, content_type='application/json',
                                    headers={'X-Webhook-Token': settings.WEBHOOK_TOKEN})
        self.assertEqual(response.status_code, 202)
        delay.assert_called_once()

    def test_only_engineer_takes_and_closes(self):
        for username in ('admin', 'orlova'):
            self.login(username)
            self.assertEqual(self.client.post('/api/incidents/1/take/').status_code, 403)
            self.assertEqual(self.client.post('/api/incidents/1/close/').status_code, 403)
        self.login('ivanov')
        response = self.client.post('/api/incidents/1/take/')
        self.assertEqual(response.json()['assignee_id'], 1)
        response = self.client.post('/api/incidents/1/close/', {'comment': 'Готово'}, content_type='application/json')
        self.assertEqual((response.json()['status'], response.json()['closed_by_id']), ('resolved', 1))

    def test_subscriptions_are_personal(self):
        self.login('orlova')
        own = self.client.get('/api/subscriptions/').json()
        self.assertEqual([s['person_id'] for s in own], [4])  # чужие подписки не видны
        petrova_sub = Subscription.objects.get(person_id=2)
        self.assertEqual(self.client.delete(f'/api/subscriptions/{petrova_sub.id}/').status_code, 404)
        created = self.client.post('/api/subscriptions/', {'service_id': 2, 'person_id': 2}, content_type='application/json')
        self.assertEqual(created.json()['person_id'], 4)  # подписаться можно только самому
        self.login('admin')
        self.assertEqual(self.client.get('/api/subscriptions/').status_code, 403)

    def test_only_manager_assigns_owners(self):
        for username in ('ivanov', 'admin'):
            self.login(username)
            self.assertEqual(self.client.post('/api/resources/3/owner/', {'person_id': 2}, content_type='application/json').status_code, 403)
        self.login('orlova')
        response = self.client.post('/api/resources/3/owner/', {'person_id': 2}, content_type='application/json')
        self.assertEqual(response.json()['owner_id'], 2)
        response = self.client.post('/api/services/1/owner/', {'person_id': 999}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        for bad in ('abc', None, [2]):
            response = self.client.post('/api/services/1/owner/', {'person_id': bad}, content_type='application/json')
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()['detail'], 'Выберите сотрудника')
