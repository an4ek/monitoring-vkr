import requests
import time
import uuid
import random
import multiprocessing

API_URL = "http://127.0.0.1:8000/api/events/zabbix/"
TOKEN = "dev-webhook-token"
RESOURCES = ["web-01", "db-01", "app-site", "srv-1c", "sw-core-01"]

def blast_events(process_id):
    count = 0
    # Каждый процесс будет долбить API без остановки
    while True:
        payload = {
            "event_id": str(uuid.uuid4()), # Уникальный ID для каждого события
            "host": random.choice(RESOURCES),
            "name": f"Шторм от процесса {process_id}",
            "severity": "critical",
            "status": "1"
        }
        try:
            # Отправляем запрос, не ждем обработки (таймаут 2 сек)
            requests.post(API_URL, json=payload, headers={"X-Webhook-Token": TOKEN}, timeout=2)
            count += 1
        except Exception:
            pass # Если API упал, просто продолжаем долбить

if __name__ == "__main__":
    print("💥 НАЧИНАЕМ АДСКИЙ ШТОРМ (50 процессов)...")
    processes = []
    
    # Запускаем 50 параллельных процессов
    for i in range(50):
        p = multiprocessing.Process(target=blast_events, args=(i,))
        p.start()
        processes.append(p)
    
    # Даем им поработать 60 секунд
    print("⏳ Штормим 60 секунд...")
    time.sleep(60)
    
    # Убиваем процессы
    for p in processes:
        p.terminate()
    print("✅ Шторм завершен.")