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

print("👀 Монитор запущен. Считаем таймауты и отказы...")
timeouts = 0
errors = 0
total_requests = 0

while True:
    start = time.time()
    total_requests += 1
    try:
        response = session.get(INC_URL, timeout=5) # Если > 5 сек — это таймаут
        if response.status_code == 200:
            incidents = response.json()
            if incidents:
                session.get(f"{INC_URL}{incidents[0]['id']}/", timeout=5)
                
            latency = (time.time() - start) * 1000
            if latency > 2000:
                print(f"🐢 МЕДЛЕННО! API отвечает за {latency:.2f} мс (превышен порог 2 сек)")
            else:
                print(f"⏱ API отвечает за {latency:.2f} мс")
    except requests.exceptions.Timeout:
        timeouts += 1
        print(f"⏰ ТАЙМАУТ! API не ответил за 5 секунд. Всего таймаутов: {timeouts}")
    except Exception as e:
        errors += 1
        print(f"💥 ОШИБКА! {e}. Всего ошибок: {errors}")
    
    time.sleep(0.5)