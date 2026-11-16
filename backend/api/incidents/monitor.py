import time
import requests

BASE_URL = "http://127.0.0.1:8000/api"
LOGIN_URL = f"{BASE_URL}/auth/login/"
INC_URL = f"{BASE_URL}/incidents/"

session = requests.Session()

print("🔑 Авторизация...")
session.get(f"{BASE_URL}/auth/csrf/")
csrf_token = session.cookies.get('csrftoken')
login_data = {"username": "ivanov", "password": "demo12345"}
headers = {"X-CSRFToken": csrf_token, "Content-Type": "application/json"}
session.post(LOGIN_URL, json=login_data, headers=headers)

print("👀 Монитор запущен. Смотрю время отклика API...")
while True:
    start = time.time()
    try:
        # 1. Запрашиваем список инцидентов
        response = session.get(INC_URL)
        if response.status_code == 200:
            incidents = response.json()
            # 2. Запрашиваем карточку первого инцидента (тяжелый JOIN)
            if incidents:
                inc_id = incidents[0]['id']
                session.get(f"{INC_URL}{inc_id}/")
        
        latency = (time.time() - start) * 1000
        print(f"⏱ API отвечает за {latency:.2f} мс")
    except Exception as e:
        print(f"💥 API упал: {e}")
    time.sleep(0.5) # Проверяем раз в полсекунды