"""Возвращает тестовые данные в исходное состояние перед показом.
    python manage.py demo_reset
"""
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection
from django.utils import timezone

from accounts.models import Profile
from api.models import Employee
from processing.models import IncomingEvent

DEMO_PASSWORD = 'demo12345'
# (логин пользователя, роль, логин сотрудника в каталоге)
DEMO_USERS = [
    ('admin', Profile.Role.ADMIN, None),
    ('ivanov', Profile.Role.ENGINEER, 'ivanov'),
    ('petrova', Profile.Role.ENGINEER, 'petrova'),
    ('orlova', Profile.Role.MANAGER, 'orlova'),
]


class Command(BaseCommand):
    help = 'Сбрасывает тестовые данные перед показом'

    def handle(self, *args, **options):
        if not settings.DEMO_COMMANDS_ENABLED:
            raise CommandError('demo_reset работает только при DJANGO_DEBUG=1')

        self.stdout.write('Сброс данных...')
        # Сырая база
        IncomingEvent.objects.using('raw').all().delete()

        # Основная база: очищаем все таблицы приложения api и обнуляем счетчики id.
        # CASCADE заодно очистит accounts_profile, он ссылается на сотрудников.
        tables = [m._meta.db_table for m in apps.get_app_config('api').get_models()]
        with connection.cursor() as cursor:
            for sql in connection.ops.sql_flush(no_style(), tables, reset_sequences=True, allow_cascade=True):
                cursor.execute(sql)

        call_command('load_mocks')

        for username, role, employee_login in DEMO_USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.set_password(DEMO_PASSWORD)
            user.is_staff = user.is_superuser = role == Profile.Role.ADMIN
            user.save()
            employee = Employee.objects.filter(login=employee_login).first() if employee_login else None
            Profile.objects.update_or_create(user=user, defaults={'role': role, 'person': employee})

        self.stdout.write(
            f'Пользователи (пароль {DEMO_PASSWORD}): '
            + ', '.join(f'{u} — {r.label}' for u, r, _ in DEMO_USERS)
        )
        self.stdout.write(self.style.SUCCESS(f'Данные сброшены ({timezone.localtime():%H:%M:%S}).'))