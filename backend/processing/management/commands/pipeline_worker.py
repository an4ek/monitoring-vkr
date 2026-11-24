"""Обработчик потока событий: landing -> поток -> кэш -> CMDB -> архив.

Нужен, когда конвейер переведен в асинхронный режим:

    ALTER DATABASE monitoring SET processing.pipeline_autostart = 'off';

Запуск:
    python manage.py pipeline_worker            # постоянно, пачками
    python manage.py pipeline_worker --once     # один проход (например, из cron)
"""
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection

RUN_SQL = """
SELECT ingested, cached, processed, failed, archived
FROM processing_pipeline_run(%s)
"""


class Command(BaseCommand):
    help = 'Разбирает поток событий: landing -> Timescale -> кэш -> CMDB -> архив'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=1000,
                            help='Размер пачки за один проход (по умолчанию 1000)')
        parser.add_argument('--interval', type=float, default=1.0,
                            help='Пауза между проходами в секундах (по умолчанию 1)')
        parser.add_argument('--once', action='store_true',
                            help='Сделать один проход и выйти')

    def run_once(self, limit):
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute(RUN_SQL, [limit])
            return cursor.fetchone()

    def report(self, row):
        if row is None:
            return
        ingested, cached, processed, failed, archived = row
        if any(row):
            self.stdout.write(
                f'Принято: {ingested}, в кэш: {cached}, обработано: {processed}, '
                f'ошибок: {failed}, в архив: {archived}'
            )

    def handle(self, *args, **options):
        limit = max(1, options['limit'])
        if options['once']:
            self.report(self.run_once(limit))
            return

        self.stdout.write('Обработчик потока запущен. Остановка — Ctrl+C.')
        try:
            while True:
                row = self.run_once(limit)
                self.report(row)
                if row is None or not any(row):
                    time.sleep(max(0.0, options['interval']))
        except KeyboardInterrupt:
            self.stdout.write('\nОбработчик остановлен.')
