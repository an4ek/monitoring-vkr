"""Возвращает тестовые данные в исходное состояние перед показом.
    python manage.py demo_reset
"""
from django.core.management import call_command
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection
from django.utils import timezone

from api.models import (
    Department, Employee, ConfigurationItem, BusinessService,
    Incident, IncidentTimeline, Event, MonitoringSystem, ServiceCI
)
from accounts.models import Profile
from processing.models import IncomingEvent
from api.models import IncidentNotifyState, Notification, ResourceState, Subscription

DEMO_PASSWORD = 'demo12345'
DEMO_USERS = [
    ('admin', Profile.Role.ADMIN, None),
    ('ivanov', Profile.Role.ENGINEER, 1),
    ('petrova', Profile.Role.ENGINEER, 2),
    ('orlova', Profile.Role.MANAGER, 4),
]


class Command(BaseCommand):
    help = 'Сбрасывает тестовые данные перед показом'

    def handle(self, *args, **options):
        if not settings.DEMO_COMMANDS_ENABLED:
            raise CommandError('demo_reset стирает данные и создает пользователей с известным паролем — только при DJANGO_DEBUG=1')

        self.stdout.write('Сброс данных...')
        # Очистка всех таблиц
        Notification.objects.all().delete()
        IncidentNotifyState.objects.all().delete()
        ResourceState.objects.all().delete()
        Subscription.objects.all().delete()
        IncomingEvent.objects.all().delete()
        IncidentTimeline.objects.all().delete()
        Event.objects.all().delete()
        Incident.objects.all().delete()
        ServiceCI.objects.all().delete()
        BusinessService.objects.all().delete()
        MonitoringSystem.objects.all().delete()
        
        # Вызываем загрузку моков (которая теперь у нас есть в api/load_mocks)
        call_command('load_mocks')

        # Сдвигаем счетчики ID, чтобы новые записи не конфликтовали
        models = [
            Department, Employee, ConfigurationItem, BusinessService,
            Incident, IncidentTimeline, Event
        ]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)

        # Отмечаем сбойными ресурсы из открытых тестовых инцидентов
        # (в нашем load_mocks создан один открытый инцидент)
        for event in Event.objects.filter(incident__status__in=['open', 'in_progress']):
            if event.ci:
                ResourceState.objects.update_or_create(
                    resource=event.ci,
                    defaults={'is_failing': True, 'severity': event.severity, 'since': event.received_at},
                )

        # Создаем пользователей
        for username, role, person_id in DEMO_USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.set_password(DEMO_PASSWORD)
            user.is_staff = user.is_superuser = role == Profile.Role.ADMIN
            user.save()
            
            # Привязываем к сотруднику (по порядку создания в load_mocks: 1=Иванов, 2=Петрова, 4=Орлова)
            emp = Employee.objects.filter(id=person_id).first() if person_id else None
            Profile.objects.update_or_create(user=user, defaults={'role': role, 'person': emp})

        self.stdout.write(
            'Пользователи (пароль ' + DEMO_PASSWORD + '): '
            + ', '.join(f'{u} — {r.label}' for u, r, _ in DEMO_USERS)
        )
        self.stdout.write(self.style.SUCCESS(f'Данные сброшены ({timezone.localtime():%H:%M:%S}).'))