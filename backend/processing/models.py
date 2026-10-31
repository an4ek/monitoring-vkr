"""Данные для приема и обработки событий и для рассылки оповещений.
"""
from django.db import models

from api.models import (
    Incident, Event, ConfigurationItem, Employee, BusinessService
)


class IncomingEvent(models.Model):
    """Событие в том виде, в каком его прислал мониторинг (после нормализации).
    Сохраняется первым шагом, до поиска ресурса, чтобы не потерять.
    """
    class Kind(models.TextChoices):
        PROBLEM = 'problem', 'Сбой'
        RECOVERY = 'recovery', 'Восстановление'

    class Status(models.TextChoices):
        NEW = 'new', 'Принято'
        ATTACHED = 'attached', 'Добавлено в инцидент'
        RECOVERED = 'recovered', 'Восстановление учтено'
        UNKNOWN_RESOURCE = 'unknown_resource', 'Ресурса нет в каталоге'

    source = models.CharField(max_length=20)
    external_id = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    resource_name = models.CharField(max_length=200)
    # Привязываем к configuration_item вместо старого Resource
    resource = models.ForeignKey(ConfigurationItem, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20)
    received_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    payload = models.JSONField(default=dict)
    # Привязываем к новому Event
    monitoring_event = models.OneToOneField(
        Event, null=True, blank=True, on_delete=models.SET_NULL, related_name='incoming',
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
    resource = models.OneToOneField(ConfigurationItem, on_delete=models.CASCADE, related_name='state')
    is_failing = models.BooleanField(default=False)
    severity = models.CharField(max_length=20, blank=True)
    since = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.resource.name}: {"сбой" if self.is_failing else "работает"}'


class Subscription(models.Model):
    """Сотрудник просит сообщать ему о сбоях сервиса, даже если он за сервис не отвечает."""
    # Меняем Person на Employee, Service на BusinessService
    person = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='subscriptions')
    service = models.ForeignKey(BusinessService, on_delete=models.CASCADE, related_name='subscriptions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['person', 'service'], name='unique_subscription'),
        ]


class Notification(models.Model):
    """Одно отправленное (или не отправленное) оповещение."""
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
    person = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL)
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
    """С какой первопричиной и какими сервисами по инциденту уже рассылали оповещения."""
    incident = models.OneToOneField(Incident, on_delete=models.CASCADE, related_name='notify_state')
    root_cause = models.ForeignKey(ConfigurationItem, null=True, on_delete=models.SET_NULL)
    service_ids = models.JSONField(default=list)