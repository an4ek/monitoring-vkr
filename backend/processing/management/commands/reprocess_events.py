"""Повторно обрабатывает события со статусом «Ошибка обработки».
Обертка над процедурой в базе: CALL reprocess_failed(). Запуск: python manage.py reprocess_events
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Повторно обрабатывает события со статусом «Ошибка обработки» (CALL reprocess_failed())'

    def handle(self, *args, **options):
        # Процедура делает COMMIT после каждого события, поэтому вызывается вне транзакции
        with connection.cursor() as cursor:
            cursor.execute('CALL reprocess_failed()')
            processed = cursor.fetchone()[0]
        self.stdout.write(self.style.SUCCESS(f'Повторно обработано событий: {processed}'))
