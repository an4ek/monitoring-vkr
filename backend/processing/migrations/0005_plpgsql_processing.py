"""Обработка событий внутри PostgreSQL (PL/pgSQL).

Повторяет логику processing/logic.py: поиск ресурса, обход графа зависимостей,
первопричина, создание или дополнение инцидента, восстановление, состояние
сервисов, история. Рассылки здесь нет.

Запуск: триггер AFTER INSERT на processing_incomingevent обрабатывает каждое
новое событие в той же транзакции, в которой его вставили.

С миграции 0006 построчный триггер заменен конвейером (landing -> поток
TimescaleDB -> кэш -> CMDB -> архив). Функции обработки из этого файла
остаются ядром: их по одной записи вызывает processing_cache_apply().

Настройки (параметры сеанса или базы):
  processing.group_window_minutes  окно склейки в минутах, по умолчанию 5
  processing.trigger_off           'on' отключает триггер (только для теста эталона)

Ручной повтор событий со статусом «Ошибка обработки»: CALL reprocess_failed();
"""
from django.db import migrations

# Тот же номер, что GROUPING_LOCK_ID в processing/logic.py
GROUPING_LOCK_ID = 7_310_001

FORWARD_SQL = r"""
-- Ресурсы, связанные с данным через зависимости в любую сторону (включая сам ресурс).
-- UNION убирает повторы, поэтому циклы в графе не приводят к бесконечному обходу.
CREATE FUNCTION processing_related_ci(p_ci bigint) RETURNS SETOF bigint
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE edges AS (
        SELECT r.source_ci_id AS a, r.target_ci_id AS b
        FROM api_cirelationship r
        JOIN api_cirelationshiptype t ON t.id = r.relationship_type_id
        WHERE t.propagates_failure
    ), walk(id) AS (
        SELECT p_ci
        UNION
        SELECT CASE WHEN e.a = w.id THEN e.b ELSE e.a END
        FROM walk w JOIN edges e ON e.a = w.id OR e.b = w.id
    )
    SELECT id FROM walk
$$;

-- Все ресурсы, от которых данный зависит прямо или через другие (без самого ресурса).
CREATE FUNCTION processing_ancestors_ci(p_ci bigint) RETURNS SETOF bigint
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE walk(id) AS (
        SELECT p_ci
        UNION
        SELECT r.target_ci_id
        FROM walk w
        JOIN api_cirelationship r ON r.source_ci_id = w.id
        JOIN api_cirelationshiptype t ON t.id = r.relationship_type_id AND t.propagates_failure
    )
    SELECT id FROM walk WHERE id <> p_ci
$$;

-- Первопричина: сбойный ресурс, у которого все ресурсы, от которых он зависит, работают.
-- Если таких нет, берется любой сбойный; из нескольких — самый ранний сбой (затем меньший id).
CREATE FUNCTION processing_find_root_cause(p_ci_ids bigint[], p_current bigint) RETURNS bigint
LANGUAGE sql STABLE AS $$
    WITH failing_here AS (
        SELECT s.resource_id AS id, s.since
        FROM api_resourcestate s
        WHERE s.is_failing AND s.resource_id = ANY (p_ci_ids)
    ), candidates AS (
        SELECT f.id, f.since
        FROM failing_here f
        WHERE NOT EXISTS (
            SELECT 1
            FROM processing_ancestors_ci(f.id) AS a(id)
            JOIN api_resourcestate s ON s.resource_id = a.id AND s.is_failing
        )
    )
    SELECT coalesce(
        (SELECT id FROM candidates ORDER BY since, id LIMIT 1),
        (SELECT id FROM failing_here ORDER BY since, id LIMIT 1),
        p_current
    )
$$;

-- Состояние сервисов по состоянию их ресурсов: down / degraded / ok.
CREATE FUNCTION processing_update_service_statuses(p_service_ids bigint[]) RETURNS void
LANGUAGE sql AS $$
    UPDATE api_businessservice b
    SET current_status = x.status
    FROM (
        SELECT bs.id,
               CASE
                   WHEN bool_or(st.is_failing AND st.severity = 'critical') THEN 'down'
                   WHEN bool_or(st.is_failing) THEN 'degraded'
                   ELSE 'ok'
               END AS status
        FROM api_businessservice bs
        LEFT JOIN api_serviceci sc ON sc.service_id = bs.id
        LEFT JOIN api_resourcestate st ON st.resource_id = sc.ci_id
        WHERE bs.id = ANY (p_service_ids)
        GROUP BY bs.id
    ) x
    WHERE b.id = x.id AND b.current_status IS DISTINCT FROM x.status
$$;

CREATE FUNCTION processing_incident_title(p_ci bigint) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE
               WHEN coalesce(c.attributes ->> 'description', '') <> ''
                   THEN 'Сбой: ' || (c.attributes ->> 'description') || ' (' || c.name || ')'
               ELSE 'Сбой: ' || c.name
           END
    FROM api_configurationitem c
    WHERE c.id = p_ci
$$;

CREATE FUNCTION processing_history(p_incident bigint, p_text text) RETURNS void
LANGUAGE sql AS $$
    INSERT INTO api_incidenttimeline (incident_id, entry_type, text, created_at, actor_id)
    VALUES (p_incident, 'system', p_text, clock_timestamp(), NULL)
$$;

CREATE FUNCTION processing_source_name(p_source text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_source
               WHEN 'zabbix' THEN 'Zabbix'
               WHEN 'prometheus' THEN 'Prometheus'
               ELSE p_source
           END
$$;

-- Система мониторинга по источнику события; создается при первом событии.
CREATE FUNCTION processing_monitoring_system(p_source text) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    sys_name text := upper(left(p_source, 1)) || lower(substr(p_source, 2));
    sys_id bigint;
BEGIN
    SELECT id INTO sys_id FROM api_monitoringsystem WHERE name = sys_name;
    IF sys_id IS NULL THEN
        INSERT INTO api_monitoringsystem
            (name, system_type, base_url, ingest_method, webhook_secret_hash, last_event_at, is_active)
        VALUES (sys_name, p_source, '', 'webhook', '', NULL, true)
        ON CONFLICT (name) DO NOTHING
        RETURNING id INTO sys_id;
        IF sys_id IS NULL THEN
            SELECT id INTO sys_id FROM api_monitoringsystem WHERE name = sys_name;
        END IF;
    END IF;
    RETURN sys_id;
END
$$;

-- Пересчет первопричины, важности и затронутых сервисов инцидента.
CREATE FUNCTION processing_refresh_incident(p_incident bigint) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    inc api_incident%ROWTYPE;
    new_root api_configurationitem%ROWTYPE;
    ci_ids bigint[];
    svc_ids bigint[];
    root_id bigint;
    old_name text;
    top_severity text;
BEGIN
    SELECT * INTO inc FROM api_incident WHERE id = p_incident FOR UPDATE;
    SELECT array_agg(DISTINCT e.ci_id) INTO ci_ids FROM api_event e WHERE e.incident_id = p_incident;

    root_id := processing_find_root_cause(ci_ids, inc.root_cause_ci_id);
    IF root_id IS NOT NULL AND root_id IS DISTINCT FROM inc.root_cause_ci_id THEN
        SELECT name INTO old_name FROM api_configurationitem WHERE id = inc.root_cause_ci_id;
        SELECT * INTO new_root FROM api_configurationitem WHERE id = root_id;
        PERFORM processing_history(
            p_incident,
            'Первопричина изменена: ' || coalesce(old_name, '—') || ' → ' || new_root.name
        );
        inc.root_cause_ci_id := root_id;
        IF new_root.owner_id IS NOT NULL THEN
            inc.responsible_id := new_root.owner_id;
        END IF;
    END IF;

    -- Самая высокая важность среди событий; при равенстве — у последнего принятого
    SELECT e.severity INTO top_severity
    FROM api_event e
    WHERE e.incident_id = p_incident
    ORDER BY CASE e.severity WHEN 'critical' THEN 2 WHEN 'warning' THEN 1 ELSE 0 END DESC,
             e.received_at DESC
    LIMIT 1;
    IF FOUND THEN
        inc.severity := top_severity;
    END IF;
    IF inc.root_cause_ci_id IS NOT NULL THEN
        inc.title := processing_incident_title(inc.root_cause_ci_id);
    END IF;

    UPDATE api_incident
    SET root_cause_ci_id = inc.root_cause_ci_id,
        responsible_id = inc.responsible_id,
        severity = inc.severity,
        title = inc.title
    WHERE id = p_incident;

    -- Затронутые сервисы: очищаем старые связи и ставим новые
    SELECT coalesce(array_agg(DISTINCT sc.service_id), '{}') INTO svc_ids
    FROM api_serviceci sc
    WHERE sc.ci_id = ANY (ci_ids);
    DELETE FROM api_incidentservice WHERE incident_id = p_incident;
    INSERT INTO api_incidentservice (incident_id, service_id, impact_level)
    SELECT p_incident, s, 'high' FROM unnest(svc_ids) AS s;

    PERFORM processing_update_service_statuses(svc_ids);
END
$$;

-- Сбой: возвращает id инцидента, к которому привязано событие.
CREATE FUNCTION processing_handle_problem(ev processing_incomingevent, ci api_configurationitem)
RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    sys_id bigint := processing_monitoring_system(ev.source);
    fp text := left(ev.external_id, 64);
    window_minutes int := coalesce(nullif(current_setting('processing.group_window_minutes', true), ''), '5')::int;
    inc_id bigint;
BEGIN
    -- Защита от повторной обработки: это событие уже записано
    SELECT e.incident_id INTO inc_id
    FROM api_event e
    WHERE e.monitoring_system_id = sys_id AND e.fingerprint = fp AND e.status = 'firing'
    ORDER BY e.received_at DESC
    LIMIT 1;
    IF inc_id IS NOT NULL THEN
        RETURN inc_id;
    END IF;

    INSERT INTO api_resourcestate (resource_id, is_failing, severity, since)
    VALUES (ci.id, true, ev.severity, ev.received_at)
    ON CONFLICT (resource_id) DO UPDATE
    SET is_failing = true,
        since = CASE WHEN api_resourcestate.is_failing THEN api_resourcestate.since ELSE ev.received_at END,
        severity = ev.severity;

    -- Открытый инцидент со свежими событиями по связанным ресурсам
    SELECT i.id INTO inc_id
    FROM api_incident i
    WHERE i.status IN ('open', 'in_progress')
      AND i.id IN (
          SELECT e.incident_id FROM api_event e
          WHERE e.received_at >= clock_timestamp() - make_interval(mins => window_minutes)
      )
      AND EXISTS (
          SELECT 1 FROM api_event e
          WHERE e.incident_id = i.id AND e.ci_id IN (SELECT processing_related_ci(ci.id))
      )
    ORDER BY i.started_at DESC
    LIMIT 1;

    IF inc_id IS NULL THEN
        INSERT INTO api_incident
            (number, title, status, severity, events_count, started_at, resolution_note,
             root_cause_ci_id, responsible_id)
        VALUES ('INC-' || upper(left(replace(gen_random_uuid()::text, '-', ''), 6)),
                processing_incident_title(ci.id), 'open', ev.severity, 1, ev.received_at, '',
                ci.id, ci.owner_id)
        RETURNING id INTO inc_id;
        PERFORM processing_history(
            inc_id,
            'Инцидент создан по событию от ' || processing_source_name(ev.source) || ': '
                || ci.name || ' — ' || ev.title
        );
    ELSE
        PERFORM processing_history(
            inc_id,
            'Добавлено событие от ' || processing_source_name(ev.source) || ': '
                || ci.name || ' — ' || ev.title
        );
    END IF;

    INSERT INTO api_event
        (monitoring_system_id, ci_id, incident_id, fingerprint, title, severity, status, labels,
         event_time, last_seen_at, resolved_at, dedup_count, received_at, raw_payload)
    VALUES (sys_id, ci.id, inc_id, fp, ev.title, ev.severity, 'firing', NULL,
            ev.received_at, ev.received_at, NULL, 1, clock_timestamp(), ev.payload);

    PERFORM processing_refresh_incident(inc_id);
    RETURN inc_id;
END
$$;

-- Восстановление ресурса: отмечаем во всех открытых инцидентах, закрываем, если все работает.
CREATE FUNCTION processing_handle_recovery(ev processing_incomingevent, ci api_configurationitem)
RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    sys_id bigint := processing_monitoring_system(ev.source);
    fp text := left('rec-' || ev.external_id, 64);
    inc_id bigint;
BEGIN
    INSERT INTO api_resourcestate (resource_id, is_failing, severity, since)
    VALUES (ci.id, false, '', NULL)
    ON CONFLICT (resource_id) DO UPDATE SET is_failing = false, since = NULL;

    PERFORM processing_update_service_statuses(
        ARRAY(SELECT sc.service_id FROM api_serviceci sc WHERE sc.ci_id = ci.id)
    );

    FOR inc_id IN
        SELECT i.id
        FROM api_incident i
        WHERE i.status IN ('open', 'in_progress')
          AND EXISTS (SELECT 1 FROM api_event e WHERE e.incident_id = i.id AND e.ci_id = ci.id)
        ORDER BY i.started_at DESC
    LOOP
        IF EXISTS (
            SELECT 1 FROM api_event e
            WHERE e.incident_id = inc_id AND e.monitoring_system_id = sys_id AND e.fingerprint = fp
        ) THEN
            CONTINUE;  -- уже обработано раньше
        END IF;

        INSERT INTO api_event
            (monitoring_system_id, ci_id, incident_id, fingerprint, title, severity, status, labels,
             event_time, last_seen_at, resolved_at, dedup_count, received_at, raw_payload)
        VALUES (sys_id, ci.id, inc_id, fp, 'Восстановлено: ' || ev.title, 'info', 'resolved', NULL,
                ev.received_at, ev.received_at, ev.received_at, 1, clock_timestamp(), ev.payload);
        PERFORM processing_history(inc_id, 'Ресурс ' || ci.name || ' восстановился');

        IF NOT EXISTS (
            SELECT 1
            FROM api_event e
            JOIN api_resourcestate s ON s.resource_id = e.ci_id AND s.is_failing
            WHERE e.incident_id = inc_id
        ) THEN
            UPDATE api_incident SET status = 'resolved', resolved_at = ev.received_at WHERE id = inc_id;
            PERFORM processing_history(inc_id, 'Инцидент закрыт автоматически: все ресурсы восстановились');
        END IF;
    END LOOP;
END
$$;

-- Разбор одного события. Результат: attached / recovery / unknown_resource.
CREATE FUNCTION processing_handle_event(ev processing_incomingevent) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    ci api_configurationitem%ROWTYPE;
BEGIN
    SELECT * INTO ci FROM api_configurationitem WHERE name = ev.resource_name ORDER BY id LIMIT 1;
    IF NOT FOUND THEN
        RETURN 'unknown_resource';
    END IF;
    IF ev.kind = 'recovery' THEN
        PERFORM processing_handle_recovery(ev, ci);
        RETURN 'recovery';
    END IF;
    PERFORM processing_handle_problem(ev, ci);
    RETURN 'attached';
END
$$;

-- Обработка события по id со статусом в той же транзакции.
-- Блокировка склейки берется до блока EXCEPTION: так она держится до конца транзакции
-- и не отпускается при откате обработки. При ошибке откатывается только обработка,
-- событие остается со статусом «Ошибка обработки» и текстом ошибки.
-- Отмена запроса (query_canceled) здесь не перехватывается: откатывается вся транзакция.
CREATE FUNCTION processing_process_event(p_id bigint) RETURNS text
LANGUAGE plpgsql AS $$
DECLARE
    ev processing_incomingevent%ROWTYPE;
    result text;
    msg text;
BEGIN
    SELECT * INTO ev FROM processing_incomingevent WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    PERFORM pg_advisory_xact_lock(__LOCK_ID__);

    BEGIN
        result := processing_handle_event(ev);
        UPDATE processing_incomingevent
        SET status = CASE result WHEN 'recovery' THEN 'recovered' ELSE result END,
            processed_at = clock_timestamp(),
            error = '',
            attempts = attempts + 1
        WHERE id = p_id;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS msg = MESSAGE_TEXT;
        UPDATE processing_incomingevent
        SET status = 'failed',
            error = left(msg, 1000),
            attempts = attempts + 1
        WHERE id = p_id;
        result := 'failed';
    END;
    RETURN result;
END
$$;

CREATE FUNCTION processing_incomingevent_after_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('processing.trigger_off', true) = 'on' THEN
        RETURN NULL;
    END IF;
    PERFORM processing_process_event(NEW.id);
    RETURN NULL;
END
$$;

CREATE TRIGGER processing_incomingevent_process
AFTER INSERT ON processing_incomingevent
FOR EACH ROW EXECUTE FUNCTION processing_incomingevent_after_insert();

-- Ручной повтор событий со статусом «Ошибка обработки».
-- COMMIT после каждого события: блокировка склейки держится на время одного события.
-- Вызывать вне явной транзакции: CALL reprocess_failed();
CREATE PROCEDURE reprocess_failed(INOUT processed integer DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE
    event_id bigint;
    current_status text;
BEGIN
    processed := 0;
    FOR event_id IN
        SELECT id FROM processing_incomingevent WHERE status = 'failed' ORDER BY received_at, id
    LOOP
        SELECT status INTO current_status FROM processing_incomingevent WHERE id = event_id FOR UPDATE;
        IF current_status = 'failed' THEN
            PERFORM processing_process_event(event_id);
            processed := processed + 1;
        END IF;
        COMMIT;
    END LOOP;
END
$$;
""".replace('__LOCK_ID__', str(GROUPING_LOCK_ID))

REVERSE_SQL = r"""
DROP PROCEDURE IF EXISTS reprocess_failed(integer);
DROP TRIGGER IF EXISTS processing_incomingevent_process ON processing_incomingevent;
DROP FUNCTION IF EXISTS processing_incomingevent_after_insert();
DROP FUNCTION IF EXISTS processing_process_event(bigint);
DROP FUNCTION IF EXISTS processing_handle_event(processing_incomingevent);
DROP FUNCTION IF EXISTS processing_handle_recovery(processing_incomingevent, api_configurationitem);
DROP FUNCTION IF EXISTS processing_handle_problem(processing_incomingevent, api_configurationitem);
DROP FUNCTION IF EXISTS processing_refresh_incident(bigint);
DROP FUNCTION IF EXISTS processing_monitoring_system(text);
DROP FUNCTION IF EXISTS processing_source_name(text);
DROP FUNCTION IF EXISTS processing_history(bigint, text);
DROP FUNCTION IF EXISTS processing_incident_title(bigint);
DROP FUNCTION IF EXISTS processing_update_service_statuses(bigint[]);
DROP FUNCTION IF EXISTS processing_find_root_cause(bigint[], bigint);
DROP FUNCTION IF EXISTS processing_ancestors_ci(bigint);
DROP FUNCTION IF EXISTS processing_related_ci(bigint);
"""


class Migration(migrations.Migration):

    dependencies = [
        ('processing', '0004_incomingevent_attempts'),
        ('api', '0002_businessservice_description'),
    ]

    operations = [
        # Списком, чтобы Django не разбивал текст на части: внутри функций есть ';' и $$
        migrations.RunSQL([FORWARD_SQL], [REVERSE_SQL]),
    ]
