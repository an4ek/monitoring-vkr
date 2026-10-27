"""Возвращает тестовые данные в исходное состояние перед показом.

    python manage.py demo_reset

Загружает тестовые данные (load_mocks), удаляет то, что появилось при прошлых
показах, отмечает сбойными ресурсы из открытых тестовых инцидентов и создает
тестовых пользователей для входа (только в режиме разработки).
"""
from django.core.management import call_command
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection
from django.utils import timezone

from api.models import Department, Incident, IncidentHistoryItem, MonitoringEvent, Person, Resource, Service
from accounts.models import Profile
from processing.models import IncidentNotifyState, IncomingEvent, Notification, ResourceState, Subscription

# Тестовые пользователи: логин, роль, id сотрудника из load_mocks
DEMO_PASSWORD = 'demo12345'
DEMO_USERS = [
    ('admin', Profile.Role.ADMIN, None),
    ('ivanov', Profile.Role.ENGINEER, 1),
    ('petrova', Profile.Role.ENGINEER, 2),
    ('orlova', Profile.Role.MANAGER, 4),
]

# id последнего тестового инцидента и события в load_mocks
MOCK_LAST_INCIDENT_ID = 4
MOCK_LAST_EVENT_ID = 11


class Command(BaseCommand):
    help = 'Сбрасывает тестовые данные перед показом'

    def handle(self, *args, **options):
        if not settings.DEMO_COMMANDS_ENABLED:
            raise CommandError('demo_reset стирает данные и создает пользователей с известным паролем — только при DJANGO_DEBUG=1')
        IncomingEvent.objects.all().delete()
        Notification.objects.all().delete()
        IncidentNotifyState.objects.all().delete()
        ResourceState.objects.all().delete()
        Subscription.objects.all().delete()
        MonitoringEvent.objects.filter(id__gt=MOCK_LAST_EVENT_ID).delete()
        Incident.objects.filter(id__gt=MOCK_LAST_INCIDENT_ID).delete()

        call_command('load_mocks')

        # load_mocks создает записи с заданными id, а счетчики id в PostgreSQL
        # при этом не сдвигаются. Сдвигаем, иначе новый инцидент получит занятый id.
        models = [Department, Person, Service, Resource, Incident, IncidentHistoryItem, MonitoringEvent]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)

        # Ресурсы из открытых тестовых инцидентов сейчас в сбое
        for event in MonitoringEvent.objects.filter(incident__status__in=['open', 'in_progress']):
            ResourceState.objects.update_or_create(
                resource=event.resource,
                defaults={'is_failing': True, 'severity': event.severity, 'since': event.received_at},
            )

        # Пример подписок: сотрудники следят за сервисами, за которые не отвечают
        Subscription.objects.create(person_id=4, service_id=1)  # Орлова — корпоративный сайт
        Subscription.objects.create(person_id=2, service_id=4)  # Петрова — 1С: Бухгалтерия

        # Кто брал в работу и закрывал тестовые инциденты (по их истории)
        Incident.objects.filter(id=2).update(assignee_id=2)
        Incident.objects.filter(id__in=[3, 4]).update(assignee_id=1, closed_by_id=1)

        for username, role, person_id in DEMO_USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.set_password(DEMO_PASSWORD)
            user.is_staff = user.is_superuser = role == Profile.Role.ADMIN  # администратор управляет пользователями в /admin/
            user.save()
            Profile.objects.update_or_create(user=user, defaults={'role': role, 'person_id': person_id})
        self.stdout.write(
            'Пользователи (пароль ' + DEMO_PASSWORD + '): '
            + ', '.join(f'{u} — {r.label}' for u, r, _ in DEMO_USERS)
        )

        self.stdout.write(self.style.SUCCESS(f'Данные сброшены ({timezone.localtime():%H:%M:%S}).'))
