"""
Специализированный генератор нагрузки для сравнения скорости ОБРАБОТКИ в БД.
Исправлено: для Архитектуры B таблица processing_incomingevent ищется в базе raw.
"""

import argparse
import asyncio
import os
import random
import time
import uuid

import aiohttp
import psycopg

# --- Конфигурация ---
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000/api/events/zabbix/")
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "dev-webhook-token")

DB_DEFAULT = "postgresql://monitoring:monitoring@localhost:5432/monitoring"
DB_RAW = "postgresql://monitoring:monitoring@localhost:5433/monitoring_raw"

RESOURCES = ["web-01", "db-01", "app-site", "srv-1c", "sw-core-01", "mq-01"]
PREFIX = f"loadtest-{uuid.uuid4().hex[:6]}-"

class DBMonitor:
    def __init__(self, arch: str):
        self.arch = arch
        # autocommit=True предотвращает блокировку сессии при ошибках
        self.conn_default = psycopg.connect(DB_DEFAULT, autocommit=True)
        self.conn_raw = psycopg.connect(DB_RAW, autocommit=True) if arch == "B" else self.conn_default

    def get_stats(self, expected_total: int) -> dict:
        stats = {
            "total_injected": 0,
            "processed_in_db": 0,
            "failed_in_db": 0,
            "events_created": 0,
            "timestamp": time.time()
        }
        
        like_pattern = f"{PREFIX}%"
        
        try:
            # ИСПРАВЛЕНИЕ: Для Arch B таблица incoming находится в базе raw
            conn_incoming = self.conn_raw if self.arch == "B" else self.conn_default
            
            with conn_incoming.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status IN ('attached', 'recovered', 'unknown_resource')) as processed,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed,
                        COUNT(*) as total
                    FROM processing_incomingevent 
                    WHERE external_id LIKE %s
                """, (like_pattern,))
                row = cur.fetchone()
                stats["processed_in_db"] = row[0]
                stats["failed_in_db"] = row[1]
                stats["total_injected"] = row[2]

            # 2. Считаем фактически созданные события в основной таблице api_event
            with self.conn_default.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) 
                    FROM api_event 
                    WHERE raw_payload->>'external_id' LIKE %s 
                       OR fingerprint LIKE %s
                """, (like_pattern.replace('%', '') + '%', f"{PREFIX}%")) 
                stats["events_created"] = cur.fetchone()[0]
                
        except Exception as e:
            print(f"\nОшибка опроса БД: {e}")
            
        return stats

    def close(self):
        self.conn_default.close()
        if self.arch == "B":
            self.conn_raw.close()


async def inject_events(total_events: int, concurrency: int):
    semaphore = asyncio.Semaphore(concurrency)
    
    async def send_one(session: aiohttp.ClientSession, event_num: int):
        payload = {
            "event_id": f"{PREFIX}{event_num}",
            "host": random.choice(RESOURCES),
            "name": f"Нагрузочный тест БД #{event_num}",
            "severity": random.choice(["3", "4", "5"]),
            "status": "1"
        }
        headers = {"X-Webhook-Token": WEBHOOK_TOKEN, "Content-Type": "application/json"}
        async with semaphore:
            try:
                async with session.post(API_URL, json=payload, headers=headers) as resp:
                    await resp.read()
                    return resp.status
            except Exception:
                return 500

    async with aiohttp.ClientSession() as session:
        tasks = [send_one(session, i) for i in range(total_events)]
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        duration = time.perf_counter() - start_time
        
        http_202 = results.count(202)
        http_errors = len(results) - http_202
        
        return {
            "duration": duration,
            "rps": total_events / duration if duration > 0 else 0,
            "http_202": http_202,
            "http_errors": http_errors
        }


async def monitor_processing(monitor: DBMonitor, total_events: int, check_interval: float = 0.5):
    print("\n⏳ Мониторинг обработки в БД...")
    history = []
    start_time = time.time()
    
    while True:
        stats = monitor.get_stats(total_events)
        history.append(stats)
        
        processed = stats["processed_in_db"]
        pct = (processed / total_events * 100) if total_events > 0 else 0
        
        print(f"\r  Обработано: {processed}/{total_events} ({pct:.1f}%) | "
              f"Ошибок: {stats['failed_in_db']} | "
              f"Создано api_event: {stats['events_created']}", end="")
        
        if processed >= total_events * 0.98 or stats["failed_in_db"] > total_events * 0.1:
            break
            
        await asyncio.sleep(check_interval)
        
    print()
    return history, time.time() - start_time


def print_report(arch: str, inject_stats: dict, process_duration: float, final_stats: dict):
    print("\n" + "="*70)
    print(f"ОТЧЁТ: Сравнение скорости обработки в БД (Архитектура {arch})")
    print("="*70)
    
    print("\n1. СКОРОСТЬ ПРИЁМА (Ingestion / INSERT)")
    print(f"   Время на отправку всех запросов : {inject_stats['duration']:.2f} сек")
    print(f"   Скорость приёма API             : {inject_stats['rps']:.1f} req/sec")
    print(f"   Успешных HTTP 202               : {inject_stats['http_202']}")
    
    print("\n2. СКОРОСТЬ ОБРАБОТКИ В БД (Processing)")
    print(f"   Время до завершения обработки   : {process_duration:.2f} сек")
    print(f"   Итого обработано триггером/воркером : {final_stats['processed_in_db']}")
    print(f"   Ошибок обработки                : {final_stats['failed_in_db']}")
    print(f"   Создано записей в api_event     : {final_stats['events_created']}")
    
    print("\n3. КЛЮЧЕВОЙ ВЫВОД")
    if arch == "A":
        print("   ➡ В Arch A время приёма и время обработки почти равны,")
        print("      так как триггер блокирует ответ API до завершения логики.")
    else:
        print("   ➡ В Arch B время приёма крайне низкое (быстрый INSERT в raw).")
        print("      Время обработки показывает реальную пропускную способность воркера.")
        print("      Разница между приёмом и обработкой — это очередь (lag), защищающая БД.")
    print("="*70 + "\n")


async def main():
    parser = argparse.ArgumentParser(description="DB Load Test for VKR")
    parser.add_argument("--arch", choices=["A", "B"], required=True, help="A = PL/pgSQL, B = Worker + 2 DBs")
    parser.add_argument("--events", type=int, default=2000, help="Количество событий для шторма")
    parser.add_argument("--concurrency", type=int, default=100, help="Одновременных запросов")
    args = parser.parse_args()

    print(f"🚀 Запуск теста для Архитектуры {args.arch}")
    print(f"📦 Генерация {args.events} событий с concurrency={args.concurrency}...")
    
    monitor = DBMonitor(args.arch)
    
    inject_stats = await inject_events(args.events, args.concurrency)
    print(f"✅ Шторм завершен за {inject_stats['duration']:.2f} сек ({inject_stats['rps']:.1f} RPS)")
    
    history, process_duration = await monitor_processing(monitor, args.events)
    
    final_stats = monitor.get_stats(args.events)
    print_report(args.arch, inject_stats, process_duration, final_stats)
    
    monitor.close()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())