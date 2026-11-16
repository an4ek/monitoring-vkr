import asyncio
import aiohttp
import time
import uuid
import random

# Настройки нагрузки
API_URL = "http://127.0.0.1:8000/api/events/zabbix/"
TOKEN = "dev-webhook-token"
TOTAL_EVENTS = 3000       # Всего событий (не бойся, это быстро)
CONCURRENCY = 50          # Сколько событий шлем одновременно (в секунду)

# Ресурсы, которые "ломаем"
RESOURCES = ["web-01", "db-01", "app-site", "srv-1c", "sw-core-01"]

async def send_event(session, event_id):
    # Имитируем JSON от Zabbix
    payload = {
        "event_id": str(uuid.uuid4()), # Уникальный ID, чтобы не было дублей
        "host": random.choice(RESOURCES),
        "name": f"Нагрузочный тест: {event_id}",
        "severity": "critical",
        "status": "1" # 1 = сбой
    }
    headers = {"X-Webhook-Token": TOKEN}
    
    try:
        async with session.post(API_URL, json=payload, headers=headers) as response:
            await response.read()
            return response.status
    except Exception as e:
        return str(e)

async def main():
    print(f"🔥 Начинаем шторм: {TOTAL_EVENTS} событий...")
    start_time = time.time()
    
    # Ограничиваем количество одновременных запросов
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async def bounded_send(session, event_id):
        async with semaphore:
            return await send_event(session, event_id)

    async with aiohttp.ClientSession() as session:
        tasks = [bounded_send(session, i) for i in range(TOTAL_EVENTS)]
        results = await asyncio.gather(*tasks)

    end_time = time.time()
    duration = end_time - start_time
    rps = TOTAL_EVENTS / duration
    
    print(f"✅ Шторм завершен!")
    print(f"⏱ Время: {duration:.2f} сек")
    print(f"🚀 Скорость: {rps:.2f} событий/сек")
    print(f"❌ Ошибки: {results.count(500) + results.count(503)} (если много, значит API не справляется)")

if __name__ == "__main__":
    asyncio.run(main())