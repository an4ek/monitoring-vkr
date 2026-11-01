"""Обработка одного события (склейка, поиск первопричины, статусы)."""
from collections import deque
from datetime import timedelta

from api.models import MonitoringSystem
from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from api.models import Incident, IncidentTimeline, Event, ConfigurationItem, BusinessService

from .models import IncomingEvent
from api.models import IncidentNotifyState, ResourceState, Notification, Subscription

GROUPING_LOCK_ID = 7_310_001
SEVERITY_RANK = {'info': 0, 'warning': 1, 'critical': 2}

OPEN_STATUSES = [Incident.Status.OPEN, Incident.Status.IN_PROGRESS]

STATUS_BY_RESULT = {
    'attached': IncomingEvent.Status.ATTACHED,
    'recovery': IncomingEvent.Status.RECOVERED,
    'unknown_resource': IncomingEvent.Status.UNKNOWN_RESOURCE,
}


# --- Граф зависимостей ---------------------------------------------------------

def _dependency_edges():
    """Все связи «ресурс -> от чего он зависит» (где propagates_failure=True)."""
    from api.models import CIRelationship
    return list(
        CIRelationship.objects
        .filter(relationship_type__propagates_failure=True)
        .values_list('source_ci_id', 'target_ci_id')
    )


def _walk(start_ids, neighbours):
    """Обход графа в ширину. Множество visited защищает от циклов."""
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
    """Первопричина — сбойный ресурс, у которого все ресурсы, от которых он зависит, работают."""
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
    pool = candidates or failing_here
    return min(pool, key=lambda rid: (states[rid].since, rid))


# --- Состояние сервисов ------------------------------------------------------

def update_service_statuses(service_ids):
    """Пересчитывает состояние сервисов по состоянию их ресурсов."""
    for service in BusinessService.objects.filter(id__in=service_ids).prefetch_related('service_cis__ci__state'):
        failing = []
        for sci in service.service_cis.all():
            if hasattr(sci.ci, 'state') and sci.ci.state.is_failing:
                failing.append(sci.ci.state)
                
        if any(s.severity == 'critical' for s in failing):
            status = 'down'
        elif failing:
            status = 'degraded'
        else:
            status = 'ok'
            
        if service.current_status != status:
            service.current_status = status
            service.save(update_fields=['current_status'])


# --- Инцидент ----------------------------------------------------------------

def _monitoring_system(source):
    system, _ = MonitoringSystem.objects.get_or_create(
        name=source.capitalize(),
        defaults={'system_type': source, 'ingest_method': 'webhook'},
    )
    return system

def _history(incident, text):
    IncidentTimeline.objects.create(incident=incident, entry_type='system', text=text)

def _incident_title(root):
    desc = root.attributes.get('description', '') if root.attributes else ''
    return f'Сбой: {desc} ({root.name})' if desc else f'Сбой: {root.name}'


def refresh_incident(incident):
    """Пересчитывает первопричину, важность и затронутые сервисы инцидента."""
    resource_ids = set(incident.events.values_list('ci_id', flat=True))

    root_id = find_root_cause(resource_ids, incident.root_cause_ci_id)
    if root_id and root_id != incident.root_cause_ci_id:
        old_root = incident.root_cause_ci
        new_root = ConfigurationItem.objects.select_related('owner').get(id=root_id)
        _history(incident, f'Первопричина изменена: {old_root.name if old_root else "—"} → {new_root.name}')
        incident.root_cause_ci = new_root
        if new_root.owner:
            incident.responsible = new_root.owner

    severities = incident.events.values_list('severity', flat=True)
    if severities:
        incident.severity = max(severities, key=lambda s: SEVERITY_RANK.get(s, 0))
    if incident.root_cause_ci:
        incident.title = _incident_title(incident.root_cause_ci)
    incident.save()

    from api.models import ServiceCI
    service_ids = set(
        ServiceCI.objects.filter(ci_id__in=resource_ids).values_list('service_id', flat=True)
    )
    
    # Очищаем старые связи и ставим новые
    from api.models import IncidentService
    IncidentService.objects.filter(incident=incident).delete()
    for sid in service_ids:
        IncidentService.objects.create(incident=incident, service_id=sid, impact_level='high')

    update_service_statuses(service_ids)


def needs_notification(incident):
    service_ids = sorted(incident.incident_services.values_list('service_id', flat=True))
    state, created = IncidentNotifyState.objects.get_or_create(incident=incident)
    if not created and state.root_cause_id == incident.root_cause_ci_id and state.service_ids == service_ids:
        return False
    state.root_cause_id = incident.root_cause_ci_id
    state.service_ids = service_ids
    state.save()
    return True


def _find_open_incident(resource_id):
    window_start = timezone.now() - timedelta(minutes=settings.EVENT_GROUP_WINDOW_MINUTES)
    recent = Event.objects.filter(received_at__gte=window_start).values('incident_id')
    return (
        Incident.objects
        .filter(status__in=OPEN_STATUSES, id__in=recent)
        .filter(events__ci_id__in=related_resource_ids(resource_id))
        .order_by('-started_at')
        .distinct()
        .first()
    )


def _handle_problem(incoming, resource):
    mon_sys = _monitoring_system(incoming.source)
    fingerprint = incoming.external_id[:64]

    # Защита от повторной обработки: это событие уже записано
    existing = Event.objects.filter(
        monitoring_system=mon_sys, fingerprint=fingerprint, status='firing',
    ).select_related('incident').first()
    if existing and existing.incident:
        return existing.incident

    at = incoming.received_at  # время приема, а не время обработки
    state, _ = ResourceState.objects.get_or_create(resource=resource)
    if not state.is_failing:
        state.is_failing = True
        state.since = at
    state.severity = incoming.severity
    state.save()

    incident = _find_open_incident(resource.id)
    if incident is None:
        incident = Incident.objects.create(
            title=_incident_title(resource),
            severity=incoming.severity,
            root_cause_ci=resource,
            responsible=resource.owner,
            started_at=at,
        )
        _history(incident, f'Инцидент создан по событию от {incoming.get_source_display()}: '
                           f'{resource.name} — {incoming.title}')
    else:
        _history(incident, f'Добавлено событие от {incoming.get_source_display()}: '
                           f'{resource.name} — {incoming.title}')

    Event.objects.create(
        incident=incident, ci=resource, monitoring_system=mon_sys,
        title=incoming.title, severity=incoming.severity, status='firing',
        fingerprint=fingerprint, event_time=at, last_seen_at=at,
        raw_payload=incoming.payload,
    )
    refresh_incident(incident)
    return incident


def _handle_recovery(incoming, resource):
    from api.models import ServiceCI
    mon_sys = _monitoring_system(incoming.source)
    fingerprint = f'rec-{incoming.external_id}'[:64]
    at = incoming.received_at

    ResourceState.objects.update_or_create(
        resource=resource, defaults={'is_failing': False, 'since': None},
    )
    update_service_statuses(ServiceCI.objects.filter(ci=resource).values_list('service_id', flat=True))

    failing = set(ResourceState.objects.filter(is_failing=True).values_list('resource_id', flat=True))
    incidents = Incident.objects.filter(status__in=OPEN_STATUSES, events__ci=resource).distinct()
    for incident in incidents:
        if Event.objects.filter(incident=incident, monitoring_system=mon_sys, fingerprint=fingerprint).exists():
            continue  # уже обработано раньше
        Event.objects.create(
            incident=incident, ci=resource, monitoring_system=mon_sys,
            title=f'Восстановлено: {incoming.title}', severity='info', status='resolved',
            fingerprint=fingerprint, event_time=at, last_seen_at=at, resolved_at=at,
            raw_payload=incoming.payload,
        )
        _history(incident, f'Ресурс {resource.name} восстановился')

        resource_ids = set(incident.events.values_list('ci_id', flat=True))
        if not (resource_ids & failing):
            incident.status = Incident.Status.RESOLVED
            incident.resolved_at = at
            incident.save(update_fields=['status', 'resolved_at'])
            _history(incident, 'Инцидент закрыт автоматически: все ресурсы восстановились')


def process(incoming):
    """Обрабатывает событие из raw. Возвращает (результат, id инцидента, нужна ли рассылка)."""
    incident_id, notify_needed = None, False

    with transaction.atomic():  # основная база: все или ничего
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [GROUPING_LOCK_ID])

        resource = ConfigurationItem.objects.filter(name=incoming.resource_name).first()
        if resource is None:
            result = 'unknown_resource'
        elif incoming.kind == IncomingEvent.Kind.RECOVERY:
            _handle_recovery(incoming, resource)
            result = 'recovery'
        else:
            incident = _handle_problem(incoming, resource)
            incident_id = incident.id
            notify_needed = needs_notification(incident)
            result = 'attached'

    # Основная база зафиксирована, теперь отмечаем событие в raw
    incoming.status = STATUS_BY_RESULT[result]
    incoming.processed_at = timezone.now()
    incoming.error = ''
    incoming.save(update_fields=['status', 'processed_at', 'error'])
    return result, incident_id, notify_needed