"""Ставит в очередь события, которые приняты, но не обработаны
(например, RabbitMQ был недоступен). Запуск: python manage.py reprocess_events
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from processing.models import IncomingEvent
from processing.tasks import process_event


class Command(BaseCommand):
    help = 'Повторно ставит в очередь необработанные события'

    def add_arguments(self, parser):
        parser.add_argument('--minutes', type=int, default=1,
                            help='Брать события, принятые раньше чем N минут назад')

    def handle(self, *args, minutes, **options):
        border = timezone.now() - timedelta(minutes=minutes)
        ids = list(IncomingEvent.objects.filter(status=IncomingEvent.Status.NEW, received_at__lt=border)
                   .values_list('id', flat=True))
        for incoming_id in ids:
            process_event.delay(incoming_id)
        self.stdout.write(self.style.SUCCESS(f'В очередь поставлено событий: {len(ids)}'))