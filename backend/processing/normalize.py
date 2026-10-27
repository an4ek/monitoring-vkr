"""Приведение событий от разных мониторингов к единому виду.

Zabbix и Alertmanager присылают данные в разном формате. После этого шага
остальной системе неважно, откуда пришло событие: у всех одни и те же поля.

Единый вид события (словарь):
    source         'zabbix' или 'prometheus'
    external_id    номер события у мониторинга (для отсева повторов)
    kind           'problem' (сбой) или 'recovery' (восстановление)
    resource_name  имя ресурса, как в каталоге (например, web-01)
    title          что случилось
    severity       'critical', 'warning' или 'info'
"""


def _clip(value, limit):
    """Обрезает слишком длинный текст, чтобы он поместился в базу."""
    return str(value)[:limit]


class InvalidEvent(ValueError):
    """Событие нельзя разобрать: не хватает обязательных полей."""


# Важность в Zabbix — число от 0 до 5
ZABBIX_SEVERITY = {
    '5': 'critical', '4': 'critical',  # «Чрезвычайная», «Высокая»
    '3': 'warning', '2': 'warning',    # «Средняя», «Предупреждение»
    '1': 'info', '0': 'info',          # «Информация», «Не классифицировано»
}


def from_zabbix(data: dict) -> list[dict]:
    """Событие от Zabbix.

    В Zabbix настраивается способ оповещения «Webhook», который при сбое и при
    восстановлении присылает JSON:
        {"event_id": "{EVENT.ID}", "status": "{EVENT.VALUE}",
         "host": "{HOST.HOST}", "name": "{EVENT.NAME}", "severity": "{EVENT.NSEVERITY}"}
    status: 1 — сбой, 0 — восстановление (можно и словами PROBLEM / RESOLVED).
    """
    if not isinstance(data, dict):
        raise InvalidEvent('Ожидается JSON-объект')
    try:
        event_id = str(data['event_id'])
        host = str(data['host'])
        name = str(data['name'])
    except KeyError as error:
        raise InvalidEvent(f'В событии Zabbix нет поля {error}') from error

    status = str(data.get('status', '1')).upper()
    kind = 'recovery' if status in ('0', 'OK', 'RESOLVED') else 'problem'
    severity = ZABBIX_SEVERITY.get(str(data.get('severity', '4')), 'warning')
    return [{
        'source': 'zabbix',
        'external_id': _clip(event_id, 200),
        'kind': kind,
        'resource_name': _clip(host, 200),
        'title': _clip(name, 300),
        'severity': severity,
    }]


def from_alertmanager(data: dict) -> list[dict]:
    """Событие от Prometheus через Alertmanager (стандартный формат его вебхука).

    В одном запросе может быть несколько алертов. Ресурс берется из метки
    resource, а если ее нет — из метки instance без номера порта.
    """
    if not isinstance(data, dict):
        raise InvalidEvent('Ожидается JSON-объект')
    alerts = data.get('alerts')
    if not isinstance(alerts, list):
        raise InvalidEvent('В событии Alertmanager нет списка alerts')

    result = []
    for alert in alerts:
        if not isinstance(alert, dict):
            raise InvalidEvent('Алерт должен быть JSON-объектом')
        labels = alert.get('labels') if isinstance(alert.get('labels'), dict) else {}
        annotations = alert.get('annotations') if isinstance(alert.get('annotations'), dict) else {}
        resource_name = labels.get('resource') or labels.get('instance', '').split(':')[0]
        if not resource_name:
            raise InvalidEvent('У алерта нет меток resource и instance')
        severity = labels.get('severity', 'warning')
        if severity not in ('critical', 'warning', 'info'):
            severity = 'warning'
        # fingerprint одинаков у сбоя и его восстановления, startsAt отличает повторные сбои
        external_id = f"{alert.get('fingerprint', labels.get('alertname', ''))}:{alert.get('startsAt', '')}"
        result.append({
            'source': 'prometheus',
            'external_id': _clip(external_id, 200),
            'kind': 'recovery' if alert.get('status') == 'resolved' else 'problem',
            'resource_name': _clip(resource_name, 200),
            'title': _clip(annotations.get('summary') or labels.get('alertname', 'Алерт Prometheus'), 300),
            'severity': severity,
        })
    return result
