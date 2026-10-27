"""Данные, которые нужны для приема и обработки событий и для рассылки оповещений.

Модели каталога и инцидентов лежат в приложении api, здесь только то,
что добавляет обработка: принятые события, текущее состояние ресурсов,
подписки и журнал отправленных оповещений.
"""
from django.db import models

from api.models import Incident, MonitoringEvent, Person, Resource, Service


class IncomingEvent(models.Model):
    """Событие в том виде, в каком его прислал мониторинг (после приведения к единому виду).

    Сохраняется первым шагом обработки, до поиска ресурса в каталоге,
    поэтому не теряется, даже если ресурса в каталоге нет.
    """

    class Kind(models.TextChoices):
        PROBLEM = 'problem', 'Сбой'
        RECOVERY = 'recovery', 'Восстановление'

    class Status(models.TextChoices):
        NEW = 'new', 'Принято'
        ATTACHED = 'attached', 'Добавлено в инцидент'
        RECOVERED = 'recovered', 'Восстановление учтено'
        UNKNOWN_RESOURCE = 'unknown_resource', 'Ресурса нет в каталоге'

    source = models.CharField(max_length=20, choices=MonitoringEvent.Source.choices)
    # Номер события у самого мониторинга: по нему отсеиваем повторы
    external_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    resource_name = models.CharField(max_length=200)
    resource = models.ForeignKey(Resource, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20, choices=MonitoringEvent.Severity.choices)
    received_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    payload = models.JSONField(default=dict)
    monitoring_event = models.OneToOneField(
        MonitoringEvent, null=True, blank=True, on_delete=models.SET_NULL, related_name='incoming',
    )

    class Meta:
        ordering = ['received_at']
        constraints = [
            models.UniqueConstraint(fields=['source', 'external_id', 'kind'], name='unique_incoming_event'),
        ]

    def __str__(self):
        return f'{self.source}:{self.external_id} {self.resource_name} ({self.kind})'


class ResourceState(models.Model):
    """Работает ресурс сейчас или нет — по последнему событию от мониторинга."""

    resource = models.OneToOneField(Resource, on_delete=models.CASCADE, related_name='state')
    is_failing = models.BooleanField(default=False)
    severity = models.CharField(max_length=20, choices=MonitoringEvent.Severity.choices, blank=True)
    since = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.resource.name}: {"сбой" if self.is_failing else "работает"}'


class Subscription(models.Model):
    """Сотрудник просит сообщать ему о сбоях сервиса, даже если он за сервис не отвечает."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='subscriptions')
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='subscriptions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['person', 'service'], name='unique_subscription'),
        ]


class Notification(models.Model):
    """Одно отправленное (или не отправленное) оповещение: кому, куда и с каким результатом."""

    class Kind(models.TextChoices):
        FIX = 'fix', 'Устранить'
        INFO = 'info', 'К сведению'

    class Channel(models.TextChoices):
        EMAIL = 'email', 'почта'
        MATTERMOST = 'mattermost', 'Mattermost'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Отправляется'
        SENT = 'sent', 'Отправлено'
        FAILED = 'failed', 'Не отправлено'

    incident = models.ForeignKey(Incident, null=True, blank=True, on_delete=models.CASCADE, related_name='notifications')
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL)
    address = models.CharField(max_length=200)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    subject = models.CharField(max_length=300)
    text = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class IncidentNotifyState(models.Model):
    """С какой первопричиной и какими сервисами по инциденту уже рассылали оповещения.

    Повторная рассылка по тому же инциденту идет, только если это изменилось.
    """

    incident = models.OneToOneField(Incident, on_delete=models.CASCADE, related_name='notify_state')
    root_cause = models.ForeignKey(Resource, null=True, on_delete=models.SET_NULL)
    service_ids = models.JSONField(default=list)
