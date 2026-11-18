"""
Генератор нагрузки для сравнения архитектур обработки событий.
Схема с кастомным воркером (raw DB + polling worker).

Запуск:
    # 1. Шторм (максимальная скорость записи, проверка, что API не блокируется)
    python load_test.py --mode storm --events 5000 --concurrency 100
    
    # 2. Постоянная смешанная нагрузка (имитация реального продакшена)
    python load_test.py --mode sustained --rps 200 --duration 60 --readers 10

Переменные окружения:
    API_URL=http://127.0.0.1:8000/api
    WEBHOOK_TOKEN=dev-webhook-token
"""

import argparse
import asyncio
import json
import os
import random
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

try:
    import aiohttp
except ImportError:
    print("Установите aiohttp: pip install aiohttp")
    raise

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ---------- Конфигурация ----------
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000/api")
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "dev-webhook-token")

RESOURCES = ["web-01", "db-01", "app-site", "srv-1c", "sw-core-01", "mq-01", "mail-01"]
SEVERITIES = ["3", "4", "5"]  # Zabbix severity

# ---------- Метрики ----------
@dataclass
class Metrics:
    write_latencies: list[float] = field(default_factory=list)
    read_latencies: list[float] = field(default_factory=list)
    write_per_second: dict[int, list[float]] = field(default_factory=lambda: defaultdict(list))
    read_per_second: dict[int, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: int = 0
    status_codes: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    start_ts: float = 0.0

    def record_write(self, latency: float, status: int, second: int):
        self.write_latencies.append(latency)
        self.write_per_second[second].append(latency)
        self.status_codes[status] += 1

    def record_read(self, latency: float, status: int, second: int):
        self.read_latencies.append(latency)
        self.read_per_second[second].append(latency)
        self.status_codes[status] += 1

    def record_error(self):
        self.errors += 1

    def percentile(self, data: list[float], p: float) -> float:
        if not data: return 0.0
        s = sorted(data)
        k = (len(s) - 1) * (p / 100)
        f = int(k)
        c = min(f + 1, len(s) - 1)
        return s[f] + (k - f) * (s[c] - s[f])

    def report(self) -> str:
        elapsed = time.time() - self.start_ts if self.start_ts else 0
        lines = ["=" * 70, "ОТЧЁТ ПО НАГРУЗКЕ (Custom Worker Architecture)", "=" * 70]
        lines.append(f"Длительность:  {elapsed:.1f} сек")
        lines.append(f"Запросов на запись (webhook): {len(self.write_latencies)}")
        lines.append(f"Запросов на чтение (API):     {len(self.read_latencies)}")
        lines.append(f"Ошибок:        {self.errors}")
        lines.append(f"HTTP-коды:     {dict(self.status_codes)}")

        if self.write_latencies:
            lines.append("\n--- ЗАПИСЬ (Ingestion, POST /api/events/) ---")
            lines.append(f"Средний RPS:       {len(self.write_latencies) / max(elapsed, 0.001):.1f}")
            lines.append(f"Latency avg:       {statistics.mean(self.write_latencies) * 1000:.1f} ms")
            lines.append(f"Latency p50:       {self.percentile(self.write_latencies, 50) * 1000:.1f} ms")
            lines.append(f"Latency p95:       {self.percentile(self.write_latencies, 95) * 1000:.1f} ms")
            lines.append(f"Latency p99:       {self.percentile(self.write_latencies, 99) * 1000:.1f} ms")
            lines.append(f"Latency max:       {max(self.write_latencies) * 1000:.1f} ms")

        if self.read_latencies:
            lines.append("\n--- ЧТЕНИЕ (Frontend polling, GET /api/incidents/) ---")
            lines.append(f"Средний RPS:       {len(self.read_latencies) / max(elapsed, 0.001):.1f}")
            lines.append(f"Latency p95:       {self.percentile(self.read_latencies, 95) * 1000:.1f} ms")
            lines.append(f"Latency max:       {max(self.read_latencies) * 1000:.1f} ms")

        return "\n".join(lines)

    def plot(self, path: str = "load_test_worker.png"):
        if not HAS_MPL or (not self.write_per_second and not self.read_per_second):
            return
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
        seconds = sorted(set(self.write_per_second) | set(self.read_per_second))

        write_rps = [len(self.write_per_second.get(s, [])) for s in seconds]
        read_rps = [len(self.read_per_second.get(s, [])) for s in seconds]
        
        ax1.plot(seconds, write_rps, label="write RPS (ingestion)", color="#1a7f37")
        ax1.plot(seconds, read_rps, label="read RPS (frontend)", color="#2f6feb")
        ax1.set_ylabel("requests / sec")
        ax1.set_title("Нагрузка по секундам")
        ax1.legend()
        ax1.grid(alpha=0.3)

        def p95_per_sec(bucket):
            return [self.percentile(bucket.get(s, []), 95) * 1000 if bucket.get(s) else 0 for s in seconds]

        ax2.plot(seconds, p95_per_sec(self.write_per_second), label="write p95", color="#1a7f37")
        ax2.plot(seconds, p95_per_sec(self.read_per_second), label="read p95", color="#2f6feb")
        ax2.set_ylabel("latency, ms")
        ax2.set_xlabel("second")
        ax2.set_title("p95 латентность по секундам (Обратите внимание на стабильность записи)")
        ax2.legend()
        ax2.grid(alpha=0.3)

        plt.tight_layout()
        plt.savefig(path, dpi=120)
        print(f"\n📊 График сохранён: {path}")


# ---------- Генерация событий ----------
def make_zabbix_payload() -> dict:
    return {
        "event_id": f"load-{uuid.uuid4().hex[:8]}", # Уникальный, чтобы не триггерить dedup
        "host": random.choice(RESOURCES),
        "name": f"Нагрузочный тест: {random.choice(['CPU high', 'Disk full', 'Ping timeout'])}",
        "severity": random.choice(SEVERITIES),
        "status": "1",
    }


# ---------- HTTP-клиент ----------
class LoadClient:
    def __init__(self, metrics: Metrics, concurrency: int):
        self.metrics = metrics
        self.sem = asyncio.Semaphore(concurrency)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=10)
        connector = aiohttp.TCPConnector(limit=0, ttl_dns_cache=60)
        self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self

    async def __aexit__(self, *exc):
        await self._session.close()

    async def send_webhook(self) -> None:
        async with self.sem:
            t0 = time.perf_counter()
            second = int(t0 - self.metrics.start_ts)
            headers = {"X-Webhook-Token": WEBHOOK_TOKEN, "Content-Type": "application/json"}
            try:
                async with self._session.post(
                    f"{API_URL}/events/zabbix/", 
                    json=make_zabbix_payload(), 
                    headers=headers
                ) as r:
                    await r.read()
                    self.metrics.record_write(time.perf_counter() - t0, r.status, second)
            except Exception:
                self.metrics.record_error()

    async def read_incidents(self) -> None:
        async with self.sem:
            t0 = time.perf_counter()
            second = int(t0 - self.metrics.start_ts)
            try:
                async with self._session.get(f"{API_URL}/incidents/") as r:
                    await r.read()
                    self.metrics.record_read(time.perf_counter() - t0, r.status, second)
            except Exception:
                self.metrics.record_error()


# ---------- Сценарии ----------
async def run_storm(args):
    """Шторм: N событий как можно быстрее. Идеально для демонстрации неблокирующей записи."""
    metrics = Metrics()
    metrics.start_ts = time.time()
    print(f"💣 Шторм: {args.events} событий, concurrency={args.concurrency}")

    async with LoadClient(metrics, args.concurrency) as client:
        tasks = [client.send_webhook() for _ in range(args.events)]
        await asyncio.gather(*tasks)

    print(metrics.report())
    metrics.plot()


async def run_sustained(args):
    """Постоянная смешанная нагрузка: эмуляция реального продакшена."""
    metrics = Metrics()
    metrics.start_ts = time.time()
    interval = 1.0 / args.rps if args.rps > 0 else 1.0
    print(f"🔥 Sustained: {args.rps} RPS (write), {args.duration} сек, readers={args.readers}")

    async with LoadClient(metrics, args.concurrency) as client:
        stop_at = time.time() + args.duration

        async def writer():
            while time.time() < stop_at:
                asyncio.create_task(client.send_webhook())
                await asyncio.sleep(interval)

        async def reader():
            while time.time() < stop_at:
                await client.read_incidents()
                await asyncio.sleep(1.0 / max(args.readers, 1))

        writers = [asyncio.create_task(writer()) for _ in range(max(1, args.writers))]
        readers = [asyncio.create_task(reader()) for _ in range(args.readers)]

        await asyncio.sleep(args.duration)
        for t in writers + readers:
            t.cancel()

    print(metrics.report())
    metrics.plot()


def main():
    p = argparse.ArgumentParser(description="Генератор нагрузки для Custom Worker архитектуры")
    subparsers = p.add_subparsers(dest="mode", required=True)
    
    p_storm = subparsers.add_parser("storm", help="Максимальный шторм записи")
    p_storm.add_argument("--events", type=int, default=5000)
    p_storm.add_argument("--concurrency", type=int, default=100)

    p_sustained = subparsers.add_parser("sustained", help="Постоянная смешанная нагрузка")
    p_sustained.add_argument("--rps", type=int, default=100)
    p_sustained.add_argument("--duration", type=int, default=60)
    p_sustained.add_argument("--concurrency", type=int, default=50)
    p_sustained.add_argument("--readers", type=int, default=5)
    p_sustained.add_argument("--writers", type=int, default=1)

    args = p.parse_args()
    if args.mode == "storm":
        asyncio.run(run_storm(args))
    elif args.mode == "sustained":
        asyncio.run(run_sustained(args))


if __name__ == "__main__":
    main()