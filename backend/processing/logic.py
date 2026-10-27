"""Обработка одного события: то, что на диаграмме последовательности
«Обработка события мониторинга» делает обработчик (шаги 5–20).

1. Сохранить событие (до поиска ресурса — чтобы не потерять).
2. Найти ресурс в каталоге.
3. Найти подходящий незакрытый инцидент или создать новый.
4. Найти первопричину.
5. Обновить состояние сервисов.
6. Решить, нужна ли рассылка оповещений.
"""
from collections import deque
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from api.models import Incident, IncidentHistoryItem, MonitoringEvent, Resource, Service

from .models import IncidentNotifyState, IncomingEvent, ResourceState

# Номер блокировки PostgreSQL: пока одно событие ищет или создает инцидент,
# другое ждет. Иначе два события одной аварии могли бы создать два инцидента.
GROUPING_LOCK_ID = 7_310_001

SEVERITY_RANK = {'info': 0, 'warning': 1, 'critical': 2}
SOURCE_NAMES = dict(MonitoringEvent.Source.choices)

OPEN_STATUSES = [Incident.Status.OPEN, Incident.Status.IN_PROGRESS]


# --- Граф зависимостей ---------------------------------------------------------

def _dependency_edges():
    """Все связи «ресурс → от чего он зависит» одним запросом."""
    through = Resource.depends_on.through
    return list(through.objects.values_list('from_resource_id', 'to_resource_id'))


def _walk(start_ids, neighbours):
    """Обход графа в ширину. Множество visited защищает от циклов в зависимостях."""
    visited = set(start_ids)
    queue = deque(start_ids)
    while queue:
        current = queue.popleft()
        for nxt in neighbours.get(current, ()):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    return visited


def related_resource_ids(resource_id):
    """Ресурсы, связанные с данным через зависимости в любую сторону."""
    neighbours = {}
    for child, parent in _dependency_edges():
        neighbours.setdefault(child, set()).add(parent)
        neighbours.setdefault(parent, set()).add(child)
    return _walk([resource_id], neighbours)


def ancestors_of(resource_id, depends_on):
    """Все ресурсы, от которых данный зависит прямо или через другие."""
    return _walk([resource_id], depends_on) - {resource_id}


# --- Первопричина ------------------------------------------------------------

def find_root_cause(resource_ids, current_root_id=None):
    """Первопричина — сбойный ресурс, у которого все ресурсы, от которых он зависит, работают.

    Если таких несколько, берем тот, что сломался раньше. Если все ресурсы
    инцидента уже работают, первопричина не меняется.
    """
    states = {
        s.resource_id: s
        for s in ResourceState.objects.filter(is_failing=True)
    }
    failing_here = [rid for rid in resource_ids if rid in states]
    if not failing_here:
        return current_root_id

    depends_on = {}
    for child, parent in _dependency_edges():
        depends_on.setdefault(child, set()).add(parent)

    candidates = [
        rid for rid in failing_here
        if not (ancestors_of(rid, depends_on) & states.keys())
    ]
    # Если подходящих нет (например, ресурсы зависят друг от друга по кругу),
    # первопричиной считаем ресурс, который сломался раньше всех
    pool = candidates or failing_here
    return min(pool, key=lambda rid: (states[rid].since, rid))


# --- Состояние сервисов ------------------------------------------------------

def update_service_statuses(service_ids):
    """Пересчитывает состояние сервисов по состоянию их ресурсов.

    Временное правило (уточняется): есть критичный сбой хотя бы одного ресурса —
    «Не работает»; есть только некритичные сбои — «С проблемами»; иначе «Работает».
    """
    for service in Service.objects.filter(id__in=service_ids).prefetch_related('resources__state'):
        failing = [
            r.state for r in service.resources.all()
            if hasattr(r, 'state') and r.state.is_failing
        ]
        if any(s.severity == 'critical' for s in failing):
            status = Service.Status.DOWN
        elif failing:
            status = Service.Status.DEGRADED
        else:
            status = Service.Status.OK
        if service.status != status:
            service.status = status
            service.save(update_fields=['status'])


# --- Инцидент ----------------------------------------------------------------

def _history(incident, text):
    IncidentHistoryItem.objects.create(incident=incident, at=timezone.now(), text=text)


def _incident_title(root):
    return f'Сбой: {root.description} ({root.name})' if root.description else f'Сбой: {root.name}'


def refresh_incident(incident):
    """Пересчитывает первопричину, важность и затронутые сервисы инцидента."""
    resource_ids = set(incident.events.values_list('resource_id', flat=True))

    root_id = find_root_cause(resource_ids, incident.root_cause_id)
    if root_id != incident.root_cause_id:
        old_root = incident.root_cause
        new_root = Resource.objects.select_related('owner').get(id=root_id)
        _history(incident, f'Первопричина изменена: {old_root.name} → {new_root.name}')
        incident.root_cause = new_root
        incident.responsible = new_root.owner

    severities = incident.events.values_list('severity', flat=True)
    incident.severity = max(severities, key=lambda s: SEVERITY_RANK[s])
    incident.title = _incident_title(incident.root_cause)
    incident.save()

    service_ids = set(
        Service.objects.filter(resources__id__in=resource_ids).values_list('id', flat=True)
    )
    incident.affected_services.set(service_ids)
    update_service_statuses(service_ids)


def needs_notification(incident):
    """Рассылать ли оповещения: да для нового инцидента и если изменились
    первопричина или набор затронутых сервисов."""
    service_ids = sorted(incident.affected_services.values_list('id', flat=True))
    state, created = IncidentNotifyState.objects.get_or_create(incident=incident)
    if not created and state.root_cause_id == incident.root_cause_id and state.service_ids == service_ids:
        return False
    state.root_cause_id = incident.root_cause_id
    state.service_ids = service_ids
    state.save()
    return True


def _find_open_incident(resource_id):
    """Незакрытый инцидент, в котором есть связанные ресурсы и события за последние N минут."""
    window_start = timezone.now() - timedelta(minutes=settings.EVENT_GROUP_WINDOW_MINUTES)
    recent = MonitoringEvent.objects.filter(received_at__gte=window_start).values('incident_id')
    return (
        Incident.objects
        .filter(status__in=OPEN_STATUSES, id__in=recent)
        .filter(events__resource_id__in=related_resource_ids(resource_id))
        .order_by('-started_at')
        .distinct()
        .first()
    )


def _handle_problem(incoming, resource):
    now = timezone.now()
    state, _ = ResourceState.objects.get_or_create(resource=resource)
    if not state.is_failing:
        state.is_failing = True
        state.since = now
    state.severity = incoming.severity
    state.save()

    source = SOURCE_NAMES[incoming.source]
    incident = _find_open_incident(resource.id)
    if incident is None:
        incident = Incident.objects.create(
            title=_incident_title(resource),
            severity=incoming.severity,
            root_cause=resource,
            responsible=resource.owner,
            started_at=now,
        )
        _history(incident, f'Инцидент создан по событию от {source}: {resource.name} — {incoming.title}')
    else:
        _history(incident, f'Добавлено событие от {source}: {resource.name} — {incoming.title}')

    incoming.monitoring_event = MonitoringEvent.objects.create(
        incident=incident, source=incoming.source, resource=resource,
        title=incoming.title, severity=incoming.severity, received_at=now,
    )
    incoming.status = IncomingEvent.Status.ATTACHED
    incoming.save()

    refresh_incident(incident)
    return incident


def _handle_recovery(incoming, resource):
    ResourceState.objects.update_or_create(
        resource=resource, defaults={'is_failing': False, 'since': None},
    )
    update_service_statuses(resource.services.values_list('id', flat=True))
    incoming.status = IncomingEvent.Status.RECOVERED

    failing = set(ResourceState.objects.filter(is_failing=True).values_list('resource_id', flat=True))
    incidents = Incident.objects.filter(status__in=OPEN_STATUSES, events__resource=resource).distinct()
    for incident in incidents:
        event = MonitoringEvent.objects.create(
            incident=incident, source=incoming.source, resource=resource,
            title=f'Восстановлено: {incoming.title}', severity=MonitoringEvent.Severity.INFO,
            received_at=timezone.now(),
        )
        incoming.monitoring_event = incoming.monitoring_event or event
        _history(incident, f'Ресурс {resource.name} восстановился')

        resource_ids = set(incident.events.values_list('resource_id', flat=True))
        if not (resource_ids & failing):
            incident.status = Incident.Status.RESOLVED
            incident.resolved_at = timezone.now()
            incident.save(update_fields=['status', 'resolved_at'])
            _history(incident, 'Инцидент закрыт автоматически: все ресурсы восстановились')
        # Первопричину при восстановлении не пересчитываем: она отвечает на вопрос,
        # с чего авария началась, и не должна меняться, пока ресурсы чинятся
    incoming.save()


def process(data):
    """Обрабатывает одно событие в едином виде (см. normalize.py).

    Возвращает (результат, id инцидента или None, нужна ли рассылка).
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [GROUPING_LOCK_ID])

        # Шаг 1: сохранить событие. Повтор того же события (тот же номер у мониторинга) отбрасываем.
        try:
            with transaction.atomic():
                incoming = IncomingEvent.objects.create(
                    source=data['source'], external_id=data['external_id'], kind=data['kind'],
                    resource_name=data['resource_name'], title=data['title'],
                    severity=data['severity'], payload=data,
                )
        except IntegrityError:
            return 'duplicate', None, False

        # Шаг 2: найти ресурс в каталоге
        resource = Resource.objects.select_related('owner').filter(name=data['resource_name']).first()
        if resource is None:
            incoming.status = IncomingEvent.Status.UNKNOWN_RESOURCE
            incoming.save(update_fields=['status'])
            return 'unknown_resource', None, False
        incoming.resource = resource

        if incoming.kind == IncomingEvent.Kind.RECOVERY:
            _handle_recovery(incoming, resource)
            return 'recovery', None, False

        incident = _handle_problem(incoming, resource)
        return 'attached', incident.id, needs_notification(incident)
