# monitor.py (запускать в отдельном терминале)
import time
import requests

URL = "http://127.0.0.1:8000/api/incidents/"
TOKEN = "dev-webhook-token" # Или используй куки, если нужно авторизоваться

print("👀 Монитор запущен. Смотрю время отклика...")
while True:
    start = time.time()
    try:
        # Если API требует авторизацию, нужно передать сессионную куку
        # Пока просто проверяем health или открытый эндпоинт
        requests.get("http://127.0.0.1:8000/api/health/") 
        latency = (time.time() - start) * 1000
        print(f"⏱ API отвечает за {latency:.2f} мс")
    except Exception as e:
        print(f"💥 API упал: {e}")
    time.sleep(1) # Проверяем раз в секунду