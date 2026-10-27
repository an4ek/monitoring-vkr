"""Проверки обработки событий. Запуск: python manage.py test processing"""
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from api.models import Incident, Service
from processing import logic
from processing.models import IncomingEvent, Notification, ResourceState
from processing.normalize import from_alertmanager, from_zabbix
from processing.tasks import send_notifications


def zabbix(event_id, host, kind='problem', severity='critical', title='Нет ответа на ping'):
    return {'source': 'zabbix', 'external_id': str(event_id), 'kind': kind,
            'resource_name': host, 'title': title, 'severity': severity}


class ProcessingTests(TestCase):
    def setUp(self):
        with mock.patch('sys.stdout'):
            call_command('demo_reset')

    def test_normalize(self):
        [z] = from_zabbix({'event_id': 1, 'host': 'web-01', 'name': 'x', 'severity': '5', 'status': '0'})
        self.assertEqual((z['kind'], z['severity']), ('recovery', 'critical'))
        [a] = from_alertmanager({'alerts': [{'status': 'firing', 'labels': {'instance': 'db-01:9187', 'severity': 'warning'},
                                             'annotations': {'summary': 's'}, 'fingerprint': 'f', 'startsAt': 't'}]})
        self.assertEqual((a['resource_name'], a['kind']), ('db-01', 'problem'))

    def test_duplicate_is_ignored(self):
        self.assertEqual(logic.process(zabbix(1, 'web-01'))[0], 'attached')
        self.assertEqual(logic.process(zabbix(1, 'web-01'))[0], 'duplicate')

    def test_unknown_resource_is_saved(self):
        self.assertEqual(logic.process(zabbix(1, 'no-such-host'))[0], 'unknown_resource')
        self.assertEqual(IncomingEvent.objects.get().status, IncomingEvent.Status.UNKNOWN_RESOURCE)

    def test_grouping_and_root_cause(self):
        _, first, notify1 = logic.process(zabbix(1, 'web-01'))
        _, second, notify2 = logic.process(zabbix(2, 'db-01'))
        self.assertEqual(first, second)  # одна авария — один инцидент
        self.assertTrue(notify1)
        self.assertEqual(Incident.objects.get(id=first).root_cause.name, 'web-01')

        _, third, notify3 = logic.process(zabbix(3, 'sw-core-01'))
        incident = Incident.objects.get(id=third)
        self.assertEqual(third, first)
        self.assertEqual(incident.root_cause.name, 'sw-core-01')  # коммутатор, от которого зависят оба
        self.assertTrue(notify3)  # первопричина изменилась — повторная рассылка
        self.assertEqual(Service.objects.get(name='Корпоративный сайт').status, 'down')

    def test_recovery_closes_incident(self):
        _, incident_id, _ = logic.process(zabbix(1, 'web-01'))
        logic.process(zabbix(2, 'sw-core-01'))
        logic.process(zabbix(2, 'sw-core-01', kind='recovery'))
        incident = Incident.objects.get(id=incident_id)
        self.assertEqual(incident.status, 'open')  # web-01 еще в сбое
        self.assertEqual(incident.root_cause.name, 'sw-core-01')  # первопричина не меняется при починке
        logic.process(zabbix(1, 'web-01', kind='recovery'))
        self.assertEqual(Incident.objects.get(id=incident_id).status, 'resolved')
        self.assertFalse(ResourceState.objects.get(resource__name='web-01').is_failing)

    @override_settings(MAILERS={'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}})
    def test_recipients_deduplicated(self):
        _, incident_id, _ = logic.process(zabbix(1, 'web-01'))
        send_notifications(incident_id)
        notes = Notification.objects.filter(incident_id=incident_id)
        people = [n.person_id for n in notes]
        self.assertEqual(len(people), len(set(people)))  # каждому одно сообщение
        fix = notes.get(kind='fix')
        self.assertEqual(fix.person.full_name, 'Иванов Сергей')  # ответственный за web-01
        self.assertTrue(all(n.status == 'sent' for n in notes))
