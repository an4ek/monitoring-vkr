"""Рассылка оповещений: функции без очереди задач.

В этой ветке события обрабатывает триггер в базе, рассылки там пока нет,
поэтому эти функции автоматически не вызываются. Их можно вызвать вручную
(например, из manage.py shell); повтор неудачной отправки не планируется сам.

  send_notifications  — разослать оповещения по инциденту (диаграмма «Рассылка оповещений»)
  retry_notification  — повторить неудачную отправку (до 3 повторов)
  notify_admin        — сообщить администратору о событии с неизвестным ресурсом
"""
from django.conf import settings

from api.models import Incident, IncidentTimeline, Notification

from . import notify
from .models import IncomingEvent


def _history(incident, text):
    if incident is None:  # оповещение администратору не привязано к инциденту
        return
    IncidentTimeline.objects.create(incident=incident, entry_type='system', text=text)


def _try_send(notification):
    notification.attempts += 1
    try:
        notify.deliver(notification)
    except Exception as error:  # noqa: BLE001 — любая ошибка отправки ведет к повтору
        notification.error = str(error)
        notification.save(update_fields=['attempts', 'error'])
        return False
    notification.status = Notification.Status.SENT
    notification.error = ''
    notification.save(update_fields=['attempts', 'status', 'error'])
    return True


def _who(notification):
    name = notification.person.full_name if notification.person else notification.address
    return f'{name} ({notification.get_channel_display()})'


def send_notifications(incident_id):
    incident = Incident.objects.select_related('root_cause_ci__owner').get(id=incident_id)
    recipients = notify.collect_recipients(incident)

    sent, retry = {'fix': [], 'info': []}, []
    for person, kind in recipients.items():
        subject, text = notify.compose(incident, kind)
        for channel, address in notify.channels_for(person):
            notification = Notification.objects.create(
                incident=incident, person=person, address=address,
                channel=channel, kind=kind, subject=subject, text=text,
            )
            if _try_send(notification):
                sent[kind].append(_who(notification))
            else:
                retry.append(_who(notification))

    # Шаг 14 на диаграмме: записать в историю, кого и куда оповестили
    parts = []
    if sent['fix']:
        parts.append('устранить — ' + ', '.join(sent['fix']))
    if sent['info']:
        parts.append('к сведению — ' + ', '.join(sent['info']))
    if parts:
        _history(incident, 'Оповещены: ' + '; '.join(parts))
    if retry:
        _history(incident, 'Не удалось отправить: ' + ', '.join(retry))


def retry_notification(notification_id):
    notification = Notification.objects.select_related('person', 'incident').get(id=notification_id)
    if notification.status != Notification.Status.PENDING:
        return
    if _try_send(notification):
        _history(notification.incident, f'Оповещение доставлено с попытки {notification.attempts}: {_who(notification)}')
        return
    # Первая попытка + 3 повтора
    if notification.attempts > settings.NOTIFY_MAX_RETRIES:
        notification.status = Notification.Status.FAILED
        notification.save(update_fields=['status'])
        _history(notification.incident, f'Не удалось оповестить после {notification.attempts} попыток: {_who(notification)}')


def notify_admin(incoming_id):
    incoming = IncomingEvent.objects.get(id=incoming_id)
    notification = Notification.objects.create(
        address=settings.ADMIN_NOTIFY_EMAIL, channel=Notification.Channel.EMAIL,
        kind=Notification.Kind.INFO,
        subject=f'Событие о ресурсе, которого нет в каталоге: {incoming.resource_name}',
        text=(
            f'Мониторинг ({incoming.get_source_display()}) прислал событие о ресурсе '
            f'«{incoming.resource_name}», которого нет в каталоге.\n'
            f'Событие: {incoming.title}\n'
            'Добавьте ресурс в каталог или исправьте его имя в мониторинге.'
        ),
    )
    _try_send(notification)
