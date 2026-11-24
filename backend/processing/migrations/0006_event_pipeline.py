"""Конвейер обработки сырых событий: landing -> Timescale -> кэш -> CMDB -> архив.

Схема потока:

1. Вебхук пишет пачку событий в `processing_incomingevent` — первую таблицу.
   Ее задача только принять данные, никакой обработки в ней нет.
2. После вставки срабатывает STATEMENT-триггер `processing_incomingevent_pipeline`.
   Он одной операцией `INSERT ... SELECT` переносит пачку в
   `processing_eventstream`. Если доступно расширение TimescaleDB, таблица
   потока становится hypertable с разбиением по времени приема.
3. Обработчик заполняет `processing_eventcache` (UNLOGGED-таблица): события
   разбираются, ресурс сопоставляется с каталогом.
4. PL/pgSQL-функции переносят подготовленные события в основную CMDB
   (`api_incident`, `api_event`, `api_resourcestate` и т.д.), очищают кэш,
   а сырые строки потока перекладывают в `processing_eventarchive`.

По умолчанию конвейер запускается в той же транзакции, что и вставка:
`processing.pipeline_autostart = 'on'`. Для асинхронной обработки:

    ALTER DATABASE monitoring SET processing.pipeline_autostart = 'off';

и отдельный процесс `python manage.py pipeline_worker`. В этом режиме триггер
только складывает пачку в поток, а разбирает ее обработчик.

Настройки (параметры сеанса или базы):
  processing.group_window_minutes   окно склейки в минутах, по умолчанию 5
  processing.pipeline_batch_size    размер пачки, по умолчанию 1000
  processing.pipeline_autostart     'off' — не обрабатывать в транзакции вставки
  processing.trigger_off            'on' отключает триггер (только для тестов)

Повтор событий со статусом «Ошибка обработки» — `CALL reprocess_failed();`
Сырые данные для повтора уже лежат в архиве, а само событие — в landing-таблице.
"""
from django.db import migrations, models

# Тот же номер, что GROUPING_LOCK_ID в processing/logic.py
GROUPING_LOCK_ID = 7_310_001

FORWARD_SQL = r"""
-- Старый построчный триггер больше не нужен: пачку разбирает конвейер.
-- Саму функцию старого триггера не удаляем — она нужна для отката миграции.
DROP TRIGGER IF EXISTS processing_incomingevent_process ON processing_incomingevent;

-- Быстрый поиск необработанных строк в первой таблице.
CREATE INDEX IF NOT EXISTS processing_incoming_pending_idx
    ON processing_incomingevent (received_at, id)
    WHERE status = 'new' AND enqueued_at IS NULL;

-- 1. Поток сырых событий. При наличии TimescaleDB станет hypertable.
CREATE TABLE IF NOT EXISTS processing_eventstream (
    stream_id     bigserial,
    incoming_id   bigint NOT NULL,
    source        varchar(20) NOT NULL,
    external_id   varchar(200) NOT NULL,
    kind          varchar(20) NOT NULL,
    resource_name varchar(200) NOT NULL,
    title         varchar(300) NOT NULL,
    severity      varchar(20) NOT NULL,
    received_at   timestamptz NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingested_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (stream_id, received_at)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        BEGIN
            CREATE EXTENSION IF NOT EXISTS timescaledb;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'TimescaleDB недоступен, поток будет обычной таблицей: %', SQLERRM;
        END;
    END IF;
END
$$;

-- create_hypertable вызываем отдельным блоком и динамически: на обычном
-- PostgreSQL этой функции нет, а конвейер должен работать и без расширения.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        BEGIN
            EXECUTE $sql$
                SELECT create_hypertable(
                    'processing_eventstream',
                    'received_at',
                    chunk_time_interval => interval '1 day',
                    if_not_exists => true
                )
            $sql$;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'processing_eventstream останется обычной таблицей: %', SQLERRM;
        END;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS processing_eventstream_time_idx
    ON processing_eventstream (received_at, stream_id);
CREATE INDEX IF NOT EXISTS processing_eventstream_stream_idx
    ON processing_eventstream (stream_id);
CREATE INDEX IF NOT EXISTS processing_eventstream_incoming_idx
    ON processing_eventstream (incoming_id);

-- 2. Кэш обработчика. UNLOGGED: при сбое базы содержимое не нужно, его можно
-- восстановить из потока. В кэше событие уже сопоставлено с ресурсом каталога.
CREATE UNLOGGED TABLE IF NOT EXISTS processing_eventcache (
    cache_id      bigserial PRIMARY KEY,
    stream_id     bigint NOT NULL UNIQUE,
    incoming_id   bigint NOT NULL,
    source        varchar(20) NOT NULL,
    external_id   varchar(200) NOT NULL,
    kind          varchar(20) NOT NULL,
    resource_name varchar(200) NOT NULL,
    title         varchar(300) NOT NULL,
    severity      varchar(20) NOT NULL,
    received_at   timestamptz NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    ci_id         bigint,
    state         varchar(20) NOT NULL DEFAULT 'ready',
    result        varchar(20),
    error         text NOT NULL DEFAULT '',
    created_at    timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS processing_eventcache_batch_idx
    ON processing_eventcache (received_at, stream_id);

-- 3. Архив: сюда переезжают строки потока после переноса в CMDB.
CREATE TABLE IF NOT EXISTS processing_eventarchive (
    archive_id    bigserial PRIMARY KEY,
    stream_id     bigint NOT NULL,
    incoming_id   bigint NOT NULL,
    source        varchar(20) NOT NULL,
    external_id   varchar(200) NOT NULL,
    kind          varchar(20) NOT NULL,
    resource_name varchar(200) NOT NULL,
    title         varchar(300) NOT NULL,
    severity      varchar(20) NOT NULL,
    received_at   timestamptz NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    result        varchar(20),
    error         text NOT NULL DEFAULT '',
    archived_at   timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS processing_eventarchive_incoming_idx
    ON processing_eventarchive (incoming_id);
CREATE INDEX IF NOT EXISTS processing_eventarchive_time_idx
    ON processing_eventarchive (received_at);

-- 4. Перенос пачки из landing-таблицы в поток.
-- Строка помечается enqueued_at, поэтому повторный триггер ее не задвоит.
CREATE OR REPLACE FUNCTION processing_stream_ingest(p_limit integer DEFAULT 1000)
RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    inserted integer;
BEGIN
    p_limit := coalesce(p_limit, 1000);
    IF p_limit < 1 THEN
        p_limit := 1000;
    END IF;

    WITH batch AS (
        UPDATE processing_incomingevent AS i
        SET enqueued_at = clock_timestamp()
        WHERE i.id IN (
            SELECT id
            FROM processing_incomingevent
            WHERE status = 'new' AND enqueued_at IS NULL
            ORDER BY received_at, id
            LIMIT p_limit
            FOR UPDATE SKIP LOCKED
        )
        RETURNING i.*
    )
    INSERT INTO processing_eventstream
        (incoming_id, source, external_id, kind, resource_name, title, severity,
         received_at, payload)
    SELECT id, source, external_id, kind, resource_name, title, severity,
           received_at, coalesce(payload, '{}'::jsonb)
    FROM batch
    ORDER BY received_at, id;

    GET DIAGNOSTICS inserted = ROW_COUNT;
    RETURN inserted;
END
$$;

-- 5. Подготовка пачки в кэше: ресурс сразу сопоставляется с каталогом.
CREATE OR REPLACE FUNCTION processing_cache_fill(p_limit integer DEFAULT 1000)
RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    cached integer;
BEGIN
    p_limit := coalesce(p_limit, 1000);
    IF p_limit < 1 THEN
        p_limit := 1000;
    END IF;

    WITH batch AS (
        SELECT s.stream_id
        FROM processing_eventstream s
        JOIN processing_incomingevent i ON i.id = s.incoming_id
        WHERE i.status = 'new'
          AND NOT EXISTS (
              SELECT 1 FROM processing_eventcache c WHERE c.stream_id = s.stream_id
          )
        ORDER BY s.received_at, s.stream_id
        LIMIT p_limit
        FOR UPDATE OF s SKIP LOCKED
    )
    INSERT INTO processing_eventcache
        (stream_id, incoming_id, source, external_id, kind, resource_name, title,
         severity, received_at, payload, ci_id)
    SELECT s.stream_id, s.incoming_id, s.source, s.external_id, s.kind,
           s.resource_name, s.title, s.severity, s.received_at, s.payload,
           (
               SELECT ci.id
               FROM api_configurationitem ci
               WHERE ci.name = s.resource_name
               ORDER BY ci.id
               LIMIT 1
           )
    FROM batch b
    JOIN processing_eventstream s ON s.stream_id = b.stream_id
    ON CONFLICT (stream_id) DO NOTHING;

    GET DIAGNOSTICS cached = ROW_COUNT;
    RETURN cached;
END
$$;

-- 6. Перенос кэша в CMDB, очистка кэша и отправка сырых строк в архив.
-- Ошибка одного события не откатывает пачку: событие получает статус failed
-- и текст ошибки, а его сырые данные все равно уходят в архив.
CREATE OR REPLACE FUNCTION processing_cache_apply(p_limit integer DEFAULT 1000)
RETURNS TABLE (processed integer, failed integer, archived integer)
LANGUAGE plpgsql AS $$
DECLARE
    c processing_eventcache%ROWTYPE;
    ev processing_incomingevent%ROWTYPE;
    handled text;
    message text;
    done_streams bigint[] := '{}';
    n_processed integer := 0;
    n_failed integer := 0;
    n_archived integer := 0;
BEGIN
    p_limit := coalesce(p_limit, 1000);
    IF p_limit < 1 THEN
        p_limit := 1000;
    END IF;

    -- Блокировка склейки: пачка обрабатывается как одна критическая секция.
    PERFORM pg_advisory_xact_lock(__LOCK_ID__);

    FOR c IN
        SELECT *
        FROM processing_eventcache
        ORDER BY received_at, stream_id
        LIMIT p_limit
        FOR UPDATE
    LOOP
        done_streams := done_streams || c.stream_id;
        handled := NULL;
        message := '';

        BEGIN
            IF c.ci_id IS NULL THEN
                -- Ресурса нет в каталоге: в CMDB писать нечего.
                handled := 'unknown_resource';
            ELSE
                -- Собираем запись того же вида, что понимают функции обработки
                -- из миграции 0005. Данные уже подготовлены в кэше.
                ev := jsonb_populate_record(NULL::processing_incomingevent, to_jsonb(c));
                handled := processing_handle_event(ev);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            GET STACKED DIAGNOSTICS message = MESSAGE_TEXT;
            handled := 'failed';
        END;

        UPDATE processing_eventcache
        SET state = CASE WHEN handled = 'failed' THEN 'failed' ELSE 'done' END,
            result = handled,
            error = left(coalesce(message, ''), 1000)
        WHERE cache_id = c.cache_id;

        UPDATE processing_incomingevent
        SET status = CASE handled
                         WHEN 'attached' THEN 'attached'
                         WHEN 'recovery' THEN 'recovered'
                         WHEN 'unknown_resource' THEN 'unknown_resource'
                         ELSE 'failed'
                     END,
            processed_at = CASE WHEN handled = 'failed' THEN NULL ELSE clock_timestamp() END,
            error = CASE WHEN handled = 'failed' THEN left(coalesce(message, ''), 1000) ELSE '' END,
            attempts = attempts + 1
        WHERE id = c.incoming_id;

        IF handled = 'failed' THEN
            n_failed := n_failed + 1;
        ELSE
            n_processed := n_processed + 1;
        END IF;
    END LOOP;

    IF cardinality(done_streams) > 0 THEN
        -- Сырые события переезжают в архив вместе с результатом обработки.
        WITH moved AS (
            DELETE FROM processing_eventstream s
            WHERE s.stream_id = ANY (done_streams)
            RETURNING s.*
        )
        INSERT INTO processing_eventarchive
            (stream_id, incoming_id, source, external_id, kind, resource_name, title,
             severity, received_at, payload, result, error)
        SELECT m.stream_id, m.incoming_id, m.source, m.external_id, m.kind,
               m.resource_name, m.title, m.severity, m.received_at, m.payload,
               cache.result, cache.error
        FROM moved m
        -- Псевдоним не может совпадать с переменной цикла c: PL/pgSQL
        -- считает такое обращение неоднозначным.
        LEFT JOIN processing_eventcache cache ON cache.stream_id = m.stream_id;

        GET DIAGNOSTICS n_archived = ROW_COUNT;

        -- Кэш очищается после успешного переноса в CMDB и архив.
        DELETE FROM processing_eventcache
        WHERE stream_id = ANY (done_streams);
    END IF;

    processed := n_processed;
    failed := n_failed;
    archived := n_archived;
    RETURN NEXT;
END
$$;

-- 7. Один запуск конвейера: забрать пачку, разложить в кэш и обработать.
CREATE OR REPLACE FUNCTION processing_pipeline_run(p_limit integer DEFAULT 1000)
RETURNS TABLE (ingested integer, cached integer, processed integer, failed integer, archived integer)
LANGUAGE plpgsql AS $$
DECLARE
    applied record;
BEGIN
    ingested := processing_stream_ingest(p_limit);
    cached := processing_cache_fill(p_limit);

    SELECT * INTO applied FROM processing_cache_apply(p_limit);
    processed := applied.processed;
    failed := applied.failed;
    archived := applied.archived;

    RETURN NEXT;
END
$$;

-- 8. Триггер на пачку INSERT. Одним вызовом переносит все новые строки в поток.
CREATE OR REPLACE FUNCTION processing_incomingevent_pipeline_trigger()
RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    batch_size integer;
    run record;
BEGIN
    IF current_setting('processing.trigger_off', true) = 'on' THEN
        RETURN NULL;
    END IF;

    batch_size := coalesce(
        nullif(current_setting('processing.pipeline_batch_size', true), ''),
        '1000'
    )::integer;
    IF batch_size < 1 THEN
        batch_size := 1000;
    END IF;

    IF coalesce(
        nullif(current_setting('processing.pipeline_autostart', true), ''),
        'on'
    ) = 'off' THEN
        -- Асинхронный режим: только складываем пачку в поток,
        -- обработчик заберет ее отдельным процессом.
        PERFORM processing_stream_ingest(batch_size);
    ELSE
        -- Если пачка больше лимита, добираем остатки: в синхронном режиме
        -- отдельного обработчика нет, и строки не должны зависнуть в landing.
        LOOP
            SELECT * INTO run FROM processing_pipeline_run(batch_size);
            EXIT WHEN coalesce(run.ingested, 0) < batch_size
                  AND coalesce(run.cached, 0) < batch_size;
        END LOOP;
    END IF;

    RETURN NULL;
END
$$;

DROP TRIGGER IF EXISTS processing_incomingevent_pipeline ON processing_incomingevent;
CREATE TRIGGER processing_incomingevent_pipeline
AFTER INSERT ON processing_incomingevent
FOR EACH STATEMENT EXECUTE FUNCTION processing_incomingevent_pipeline_trigger();
""".replace('__LOCK_ID__', str(GROUPING_LOCK_ID))

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS processing_incomingevent_pipeline ON processing_incomingevent;
DROP INDEX IF EXISTS processing_incoming_pending_idx;
DROP FUNCTION IF EXISTS processing_incomingevent_pipeline_trigger();
DROP FUNCTION IF EXISTS processing_pipeline_run(integer);
DROP FUNCTION IF EXISTS processing_cache_apply(integer);
DROP FUNCTION IF EXISTS processing_cache_fill(integer);
DROP FUNCTION IF EXISTS processing_stream_ingest(integer);

DROP TABLE IF EXISTS processing_eventcache;
DROP TABLE IF EXISTS processing_eventarchive;
DROP TABLE IF EXISTS processing_eventstream;

-- Возвращаем построчный триггер из миграции 0005.
DROP TRIGGER IF EXISTS processing_incomingevent_process ON processing_incomingevent;
CREATE TRIGGER processing_incomingevent_process
AFTER INSERT ON processing_incomingevent
FOR EACH ROW EXECUTE FUNCTION processing_incomingevent_after_insert();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('processing', '0005_plpgsql_processing'),
        ('api', '0002_businessservice_description'),
    ]

    operations = [
        migrations.AddField(
            model_name='incomingevent',
            name='enqueued_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        # Списком, чтобы Django не разбивал текст на части: внутри функций есть ';' и $$
        migrations.RunSQL([FORWARD_SQL], [REVERSE_SQL]),
    ]
