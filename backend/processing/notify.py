"""Рассылка оповещений: кому писать, что писать и как отправить.

Получатели (диаграмма «Рассылка оповещений», шаги 5–7):
  - ответственный за ресурс-первопричину — «устранить»;
  - ответственные за затронутые сервисы — «к сведению»;
  - подписчики затронутых сервисов — «к сведению».
Списки объединяются, чтобы каждый получил одно сообщение.
"""
import json
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

from api.models import Incident, Person

from .models import Notification, Subscription


def collect_recipients(incident: Incident) -> dict[Person, str]:
    """Возвращает {сотрудник: 'fix' или 'info'} без повторов."""
    recipients: dict[Person, str] = {}
    services = list(incident.affected_services.select_related('owner'))

    for service in services:
        recipients[service.owner] = Notification.Kind.INFO
    subscriptions = Subscription.objects.filter(service__in=services).select_related('person')
    for subscription in subscriptions:
        recipients[subscription.person] = Notification.Kind.INFO
    # Ответственный за первопричину получает «устранить», даже если он есть и в других списках
    recipients[incident.root_cause.owner] = Notification.Kind.FIX
    return recipients


def channels_for(person: Person) -> list[tuple[str, str]]:
    """Куда отправлять: почта всегда, Mattermost — если он подключен."""
    result = [(Notification.Channel.EMAIL, person.email)]
    if settings.MATTERMOST_WEBHOOK_URL and person.mattermost:
        result.append((Notification.Channel.MATTERMOST, person.mattermost))
    return result


def compose(incident: Incident, kind: str) -> tuple[str, str]:
    """Тема и текст оповещения."""
    root = incident.root_cause
    services = ', '.join(incident.affected_services.values_list('name', flat=True)) or 'нет'
    action = 'Устранить' if kind == Notification.Kind.FIX else 'К сведению'
    subject = f'[{action}] Инцидент №{incident.id}: {incident.title}'
    lines = [
        f'{action}.',
        f'Инцидент №{incident.id}: {incident.title}',
        f'Первопричина: {root.name} — {root.description}',
        f'Затронутые сервисы: {services}',
        f'Ответственный за первопричину: {root.owner.full_name}',
    ]
    if kind == Notification.Kind.FIX and root.runbook_url:
        lines.append(f'Инструкция: {root.runbook_url}')
    lines.append(f'Карточка инцидента: {settings.FRONTEND_URL}/incidents/{incident.id}')
    return subject, '\n'.join(lines)


def deliver(notification: Notification) -> None:
    """Отправляет одно оповещение. При ошибке выбрасывает исключение."""
    if notification.channel == Notification.Channel.EMAIL:
        send_mail(
            notification.subject, notification.text,
            settings.DEFAULT_FROM_EMAIL, [notification.address],
        )
        return

    # Mattermost: входящий вебхук канала, получателя упоминаем через @
    body = json.dumps({'text': f'{notification.address} {notification.subject}\n{notification.text}'})
    request = urllib.request.Request(
        settings.MATTERMOST_WEBHOOK_URL, data=body.encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status >= 300:
            raise RuntimeError(f'Mattermost ответил {response.status}')
