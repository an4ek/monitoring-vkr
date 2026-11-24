from django.db import models


class IncomingEvent(models.Model):
    """Первая таблица конвейера: только прием события от вебхука.

    После вставки пачки триггер переносит строки в processing_eventstream
    (TimescaleDB), откуда их забирает обработчик. payload — тело запроса так,
    как его прислал мониторинг. enqueued_at — когда строка ушла в поток."""
    class Source(models.TextChoices):
        ZABBIX = 'zabbix', 'Zabbix'
        PROMETHEUS = 'prometheus', 'Prometheus'

    class Kind(models.TextChoices):
        PROBLEM = 'problem', 'Сбой'
        RECOVERY = 'recovery', 'Восстановление'

    class Status(models.TextChoices):
        NEW = 'new', 'Принято'
        ATTACHED = 'attached', 'Обработано'
        RECOVERED = 'recovered', 'Восстановление обработано'
        UNKNOWN_RESOURCE = 'unknown_resource', 'Ресурса нет в каталоге'
        FAILED = 'failed', 'Ошибка обработки'

    source = models.CharField(max_length=20, choices=Source.choices)
    external_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    resource_name = models.CharField(max_length=200)
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20)
    received_at = models.DateTimeField(auto_now_add=True)
    enqueued_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    error = models.TextField(blank=True)
    attempts = models.IntegerField(default=0, db_default=0)  # сколько раз событие обрабатывали
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ['received_at']
        constraints = [
            models.UniqueConstraint(fields=['source', 'external_id', 'kind'], name='unique_incoming_event'),
        ]
        indexes = [models.Index(fields=['status', 'received_at'])]