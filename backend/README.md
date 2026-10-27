# Бэкенд

Django + Django REST Framework (API-сервер) и Celery (обработчик событий и оповещений).

| Приложение | Что внутри |
|---|---|
| `api/` | Каталог (отделы, сотрудники, сервисы, ресурсы с зависимостями), инциденты, история, события; API на чтение; тестовые данные (`load_mocks`) |
| `processing/` | Прием событий от Zabbix и Alertmanager, обработка в Celery (группировка в инцидент, первопричина, состояние сервисов, автозакрытие), рассылка оповещений, кнопки «Взять в работу» и «Закрыть», подписки |

## Запуск

Сначала поднять инфраструктуру (PostgreSQL, RabbitMQ, Mailpit): `cd infra && docker compose up -d`.

```
cd backend
python -m venv venv
venv\Scripts\activate            # Windows   (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python manage.py migrate
python manage.py demo_reset      # тестовые данные
```

Дальше нужны два окна терминала (в обоих активировать venv):

```
python manage.py runserver                 # API-сервер, http://localhost:8000/api/
celery -A config worker -l info --pool=solo   # обработчик событий (на Windows обязательно --pool=solo)
```

И фронтенд: `cd frontend && npm run dev`, открыть http://localhost:5173.

## Показ: авария коммутатора

```
python manage.py demo_reset              # вернуть тестовые данные в исходное состояние
python manage.py demo_failure            # прислать события о сбое (как Zabbix и Alertmanager)
python manage.py demo_failure --recover  # прислать события о восстановлении
```

Что увидеть:

1. В журнале инцидентов через несколько секунд появляется новый инцидент. Сначала первопричина `web-01`, а когда приходит событие о коммутаторе, она меняется на `sw-core-01`.
2. В карточке инцидента пять событий: коммутатор отмечен как первопричина, остальные как следствия. На странице «Сервисы» сайт и 1С в состоянии «Не работает».
3. В Mailpit (http://localhost:8025) лежат письма: Иванову — «Устранить», остальным — «К сведению».
4. Выбрать себя в шапке справа и нажать «Взять в работу», затем «Закрыть». В истории видно, кто и когда.
5. Или вместо ручного закрытия выполнить `demo_failure --recover`: инцидент закроется сам, сервисы вернутся в «Работает».

Проверки: `python manage.py test processing`.

## Прием событий

| Адрес | Кто присылает | Формат |
|---|---|---|
| `POST /api/events/zabbix/` | Zabbix, способ оповещения «Webhook» | `{"event_id": "{EVENT.ID}", "status": "{EVENT.VALUE}", "host": "{HOST.HOST}", "name": "{EVENT.NAME}", "severity": "{EVENT.NSEVERITY}"}` |
| `POST /api/events/alertmanager/` | Alertmanager, `webhook_configs` | стандартный формат Alertmanager; ресурс берется из метки `resource` или `instance` |

Ответ сразу `202 Принято`, обработка идет в Celery. Если в настройках задан `WEBHOOK_TOKEN`, мониторинг должен передавать его в заголовке `X-Webhook-Token`.

## Настройки (переменные окружения)

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT` | `localhost`, `5432` | База данных |
| `CELERY_BROKER_URL` | `amqp://monitoring:monitoring@localhost:5672//` | RabbitMQ |
| `EMAIL_HOST`, `EMAIL_PORT` | `localhost`, `1025` | Почта (Mailpit) |
| `MATTERMOST_WEBHOOK_URL` | пусто | Входящий вебхук канала Mattermost; пусто — в Mattermost не пишем |
| `EVENT_GROUP_WINDOW_MINUTES` | `5` | Окно группировки событий в инцидент |
| `WEBHOOK_TOKEN` | пусто | Ключ для приема событий |

## Что пока упрощено

- Входа в систему и ролей нет: кто нажал кнопку, выбирается в шапке сайта.
- Правило состояния сервиса временное: критичный сбой ресурса — «Не работает», некритичный — «С проблемами».
