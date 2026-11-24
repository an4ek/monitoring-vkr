"""
Воркер обработки сырых событий вместо Celery.

Очередь = таблица IncomingEvent в базе raw.
Статусы: NEW -> PROCESSING -> ATTACHED | FAILED.

Нужные поля модели IncomingEvent (см. миграцию в конце файла):
    status        - добавить значение PROCESSING
    attempts      - сколько раз брали в работу
    locked_at     - когда взяли в работу (для возврата зависших)
    available_at  - не раньше какого времени можно брать (повтор с задержкой)
"""
import logging
import os
import signal
import threading
from datetime import timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import (  # noqa: E402
    DatabaseError,
    close_old_connections,
    connection,
    transaction,
)
from django.db.models import F  # noqa: E402
from django.utils import timezone  # noqa: E402

from processing import logic  # noqa: E402
from processing.models import IncomingEvent  # noqa: E402

log = logging.getLogger("worker")

BATCH_SIZE = 100
MAX_ATTEMPTS = 5            # после этого событие уходит в FAILED
STUCK_AFTER = timedelta(minutes=5)   # PROCESSING дольше этого считается зависшим
RETRY_BASE_SECONDS = 10     # задержка повтора: 10, 20, 40, 80 сек
IDLE_MIN, IDLE_MAX = 0.1, 1.0

# Ошибки самого события: повторять бессмысленно, сразу FAILED.
# Подгоните под исключения, которые реально бросает logic.process.
PERMANENT_ERRORS = (ValueError, KeyError, TypeError)

stop = threading.Event()


def _handle_signal(signum, frame):
    log.info("Получен сигнал %s, завершаюсь после текущей пачки", signum)
    stop.set()


def requeue_stuck():
    """Возвращает в очередь события, которые воркер взял и не закончил (упал)."""
    n = (
        IncomingEvent.objects.using("raw")
        .filter(
            status=IncomingEvent.Status.PROCESSING,
            locked_at__lt=timezone.now() - STUCK_AFTER,
        )
        .update(status=IncomingEvent.Status.NEW, locked_at=None)
    )
    if n:
        log.warning("Возвращено зависших событий: %s", n)


def claim_batch(batch_size=BATCH_SIZE):
    """
    Атомарно забирает пачку: выбирает NEW и тут же помечает PROCESSING.
    Блокировка select_for_update живёт только внутри транзакции, поэтому
    без смены статуса другой воркер взял бы те же строки (так было раньше).
    """
    now = timezone.now()
    with transaction.atomic(using="raw"):
        events = list(
            IncomingEvent.objects.using("raw")
            .select_for_update(skip_locked=True)
            .filter(status=IncomingEvent.Status.NEW, available_at__lte=now)
            .order_by("received_at")[:batch_size]
        )
        if events:
            IncomingEvent.objects.using("raw").filter(
                id__in=[e.id for e in events]
            ).update(
                status=IncomingEvent.Status.PROCESSING,
                locked_at=now,
                attempts=F("attempts") + 1,
            )
            for e in events:
                e.attempts += 1
    return events


def _lock_key(incoming):
    """
    Ключ, по которому события обрабатываются строго по очереди.
    Нужен, чтобы resolved не обогнал firing того же объекта, если воркеров
    несколько. Подставьте поле fingerprint, когда оно появится в модели.
    """
    return getattr(incoming, "fingerprint", None) or incoming.id


def process_one(incoming):
    """Обрабатывает событие; запись в основную базу атомарна."""
    key = hash(str(_lock_key(incoming))) & 0x7FFFFFFFFFFFFFFF
    with transaction.atomic(using="default"):
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", [key])
        return logic.process(incoming)


def mark_done(incoming):
    incoming.status = IncomingEvent.Status.ATTACHED
    incoming.processed_at = timezone.now()
    incoming.error = ""
    incoming.locked_at = None
    incoming.save(
        using="raw",
        update_fields=["status", "processed_at", "error", "locked_at"],
    )


def mark_failed_or_retry(incoming, exc):
    permanent = isinstance(exc, PERMANENT_ERRORS)
    incoming.error = f"{type(exc).__name__}: {exc}"[:500]
    incoming.locked_at = None
    if permanent or incoming.attempts >= MAX_ATTEMPTS:
        incoming.status = IncomingEvent.Status.FAILED
        incoming.save(using="raw", update_fields=["status", "error", "locked_at"])
        log.error("FAILED id=%s попыток=%s: %s", incoming.id, incoming.attempts, exc)
    else:
        delay = RETRY_BASE_SECONDS * 2 ** (incoming.attempts - 1)
        incoming.status = IncomingEvent.Status.NEW
        incoming.available_at = timezone.now() + timedelta(seconds=delay)
        incoming.save(
            using="raw",
            update_fields=["status", "error", "locked_at", "available_at"],
        )
        log.warning("Повтор id=%s через %s с: %s", incoming.id, delay, exc)


def notify(incident_ids):
    """Оповещения отдельно от обработки: их сбой не должен портить событие."""
    from processing.tasks import send_notifications

    for incident_id in incident_ids:
        try:
            send_notifications(incident_id)
        except Exception:
            log.exception("Ошибка оповещения по инциденту %s", incident_id)


def run_worker():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info("Воркер запущен")

    idle = IDLE_MIN
    last_requeue = 0.0

    while not stop.is_set():
        try:
            close_old_connections()  # иначе долгий процесс держит протухшие соединения

            if timezone.now().timestamp() - last_requeue > 60:
                requeue_stuck()
                last_requeue = timezone.now().timestamp()

            events = claim_batch()
            if not events:
                stop.wait(idle)                    # просыпается сразу по сигналу
                idle = min(idle * 1.5, IDLE_MAX)   # постепенно увеличиваем паузу
                continue
            idle = IDLE_MIN

            to_notify = []
            for incoming in events:
                try:
                    result, incident_id, notify_needed = process_one(incoming)
                    mark_done(incoming)
                    log.info("OK id=%s результат=%s", incoming.id, result)
                    if notify_needed and incident_id and incident_id not in to_notify:
                        to_notify.append(incident_id)
                except Exception as exc:
                    mark_failed_or_retry(incoming, exc)

            notify(to_notify)

        except DatabaseError:
            log.exception("База недоступна, пауза 5 с")
            stop.wait(5)
        except Exception:
            log.exception("Непредвиденная ошибка воркера, пауза 5 с")
            stop.wait(5)

    log.info("Воркер остановлен")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_worker()


# --- Что добавить в processing/models.py (IncomingEvent) -------------------
#
#   class Status(models.TextChoices):
#       NEW = "new"
#       PROCESSING = "processing"      # <- новое
#       ATTACHED = "attached"
#       FAILED = "failed"
#
#   attempts = models.PositiveSmallIntegerField(default=0)
#   locked_at = models.DateTimeField(null=True, blank=True)
#   available_at = models.DateTimeField(default=timezone.now, db_index=True)
#
#   class Meta:
#       indexes = [models.Index(fields=["status", "available_at", "received_at"])]
#
# Затем: python manage.py makemigrations processing && migrate --database=raw