"""Имитирует аварию: присылает события так, как их прислали бы Zabbix и Alertmanager.

    python manage.py demo_failure            # сбой
    python manage.py demo_failure --recover  # восстановление

Сценарий: ломается центральный коммутатор sw-core-01. Сначала приходят события
о серверах за ним (web-01, db-01, srv-1c) и о приложении сайта, и только потом
о самом коммутаторе. Система собирает все в один инцидент и, когда приходит
событие о коммутаторе, меняет первопричину на него.

События отправляются по HTTP на API-сервер, то есть проходят тот же путь,
что и настоящие: прием → очередь RabbitMQ → обработчик Celery.
"""
import json
import time
import urllib.request
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand

ZABBIX_EVENTS = [
    ('web-01', 'Нет ответа на ping', '4'),
    ('db-01', 'PostgreSQL: нет ответа на порту 5432', '4'),
]
ALERTMANAGER_EVENTS = [
    ('app-site', 'SiteDown', 'Сайт не отвечает на HTTP-проверку', 'critical'),
]
ZABBIX_LATE_EVENTS = [
    ('srv-1c', 'Нет ответа на ping', '4'),
    ('sw-core-01', 'Коммутатор не отвечает на ping', '5'),
]


class Command(BaseCommand):
    help = 'Имитирует аварию коммутатора (или ее устранение с --recover)'

    def add_arguments(self, parser):
        parser.add_argument('--url', default='http://localhost:8000/api', help='Адрес API-сервера')
        parser.add_argument('--pause', type=float, default=2.0, help='Пауза между событиями, секунд')
        parser.add_argument('--recover', action='store_true', help='Прислать события о восстановлении')

    def post(self, url, payload):
        headers = {'Content-Type': 'application/json'}
        if settings.WEBHOOK_TOKEN:
            headers['X-Webhook-Token'] = settings.WEBHOOK_TOKEN
        request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def handle(self, *args, url, pause, recover, **options):
        # Номера событий: при сбое придумываем новые, при восстановлении берем те же
        ids_file = settings.BASE_DIR / '.demo_event_ids.json'
        if recover:
            ids = json.loads(ids_file.read_text()) if ids_file.exists() else {}
        else:
            ids = {}

        def zabbix(host, name, severity):
            event_id = ids.setdefault(host, str(uuid.uuid4().int)[:8])
            payload = {'event_id': event_id, 'host': host, 'name': name,
                       'severity': severity, 'status': '0' if recover else '1'}
            return self.post(f'{url}/events/zabbix/', payload)

        def alertmanager(resource, alertname, summary, severity):
            fingerprint = ids.setdefault(resource, uuid.uuid4().hex[:16])
            starts_at = ids.setdefault(resource + ':start', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            payload = {'alerts': [{
                'status': 'resolved' if recover else 'firing',
                'labels': {'alertname': alertname, 'resource': resource, 'severity': severity},
                'annotations': {'summary': summary},
                'startsAt': starts_at, 'fingerprint': fingerprint,
            }]}
            return self.post(f'{url}/events/alertmanager/', payload)

        steps = (
            [('Zabbix', e[0], lambda e=e: zabbix(*e)) for e in ZABBIX_EVENTS]
            + [('Alertmanager', e[0], lambda e=e: alertmanager(*e)) for e in ALERTMANAGER_EVENTS]
            + [('Zabbix', e[0], lambda e=e: zabbix(*e)) for e in ZABBIX_LATE_EVENTS]
        )
        if recover:
            steps.reverse()  # сначала чинится коммутатор, потом остальное

        what = 'восстановление' if recover else 'сбой'
        for source, resource, send in steps:
            status, body = send()
            self.stdout.write(f'{source} → {what} {resource}: {status} {body["status"]}')
            time.sleep(pause)

        ids_file.write_text(json.dumps(ids))
        self.stdout.write(self.style.SUCCESS('Готово. Откройте журнал инцидентов.'))
