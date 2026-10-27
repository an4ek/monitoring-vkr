# Бэкенд

Django + Django REST Framework (API-сервер) и Celery (обработчик событий и оповещений).

| Приложение | Что внутри |
|---|---|
| `api/` | Каталог (отделы, сотрудники, сервисы, ресурсы с зависимостями), инциденты, история, события; API на чтение; тестовые данные (`load_mocks`) |
| `processing/` | Прием событий от Zabbix и Alertmanager, обработка в Celery (группировка в инцидент, первопричина, состояние сервисов, автозакрытие), рассылка оповещений, кнопки «Взять в работу» и «Закрыть», подписки |
| `accounts/` | Вход по логину и паролю, роли: администратор, инженер, руководитель |

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
celery -A config worker -l info --pool=solo   # обработчик событий (--pool=solo нужен и на Windows, и на macOS)
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
4. Войти как инженер (`ivanov`) и нажать «Взять в работу», затем «Закрыть». В журнале и карточке видно, кто взял и кто закрыл. Под руководителем (`orlova`) и администратором (`admin`) этих кнопок нет.
5. Или вместо ручного закрытия выполнить `demo_failure --recover`: инцидент закроется сам, сервисы вернутся в «Работает».

Проверки: `python manage.py test processing accounts`.

## Вход и роли

`demo_reset` создает тестовых пользователей, пароль у всех `demo12345`:

| Логин | Роль | Что может |
|---|---|---|
| `admin` | Администратор | Смотреть журнал; управлять пользователями, ролями и каталогом в админке http://localhost:8000/admin/ |
| `ivanov`, `petrova` | Инженер | Брать инциденты в работу и закрывать их, свои подписки |
| `orlova` | Руководитель | Смотреть журнал, первопричины и сервисы, свои подписки |

Без входа API отдает только `/api/health/`. Вход по сессии Django: cookie сессии недоступна JavaScript, изменяющие запросы защищены CSRF-токеном.

## Прием событий

| Адрес | Кто присылает | Формат |
|---|---|---|
| `POST /api/events/zabbix/` | Zabbix, способ оповещения «Webhook» | `{"event_id": "{EVENT.ID}", "status": "{EVENT.VALUE}", "host": "{HOST.HOST}", "name": "{EVENT.NAME}", "severity": "{EVENT.NSEVERITY}"}` |
| `POST /api/events/alertmanager/` | Alertmanager, `webhook_configs` | стандартный формат Alertmanager; ресурс берется из метки `resource` или `instance` |

Ответ сразу `202 Принято`, обработка идет в Celery. Мониторинг обязан передавать секретный ключ в заголовке `X-Webhook-Token`, иначе ответ `403`. При разработке ключ `dev-webhook-token`.

## Настройки (переменные окружения)

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `POSTGRES_HOST`, `POSTGRES_PORT` | `localhost`, `5432` | База данных |
| `CELERY_BROKER_URL` | `amqp://monitoring:monitoring@localhost:5672//` | RabbitMQ |
| `EMAIL_HOST`, `EMAIL_PORT` | `localhost`, `1025` | Почта (Mailpit) |
| `MATTERMOST_WEBHOOK_URL` | пусто | Входящий вебхук канала Mattermost; пусто — в Mattermost не пишем |
| `EVENT_GROUP_WINDOW_MINUTES` | `5` | Окно группировки событий в инцидент |
| `WEBHOOK_TOKEN` | `dev-webhook-token` (только при разработке) | Ключ для приема событий |
| `DJANGO_DEBUG` | `1` | `0` на сервере: тогда обязательны свои `DJANGO_SECRET_KEY` и `WEBHOOK_TOKEN`, а `demo_reset` не работает |
| `DJANGO_SECRET_KEY` | ключ разработки | Секретный ключ Django |
| `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | `localhost,127.0.0.1`, `http://localhost:5173` | С каких адресов можно обращаться |

## Что пока упрощено

- Пользователями и ролями администратор управляет через админку Django, отдельной страницы на сайте пока нет.
- Нет ограничения числа попыток входа.
- Правило состояния сервиса временное: критичный сбой ресурса — «Не работает», некритичный — «С проблемами».
