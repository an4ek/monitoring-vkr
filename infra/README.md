# Инфраструктура для разработки

PostgreSQL, RabbitMQ и Mailpit в Docker.

## Запуск

```
cd infra
cp .env.example .env
docker compose up -d
docker compose ps
```

Все три сервиса должны быть в статусе `running` (у PostgreSQL и RabbitMQ — `healthy`).

## Что где

| Сервис | Адрес | Зачем |
|---|---|---|
| PostgreSQL | `localhost:5432` | База данных системы |
| RabbitMQ | `localhost:5672`, панель `http://localhost:15672` | Брокер для Celery и очередь событий |
| Mailpit | SMTP `localhost:1025`, веб `http://localhost:8025` | Перехватывает письма: всё, что отправит система, видно в веб-интерфейсе, наружу ничего не уходит |

Логин и пароль везде по умолчанию `monitoring` / `monitoring` (меняются в `.env`).

## Настройки для бэкенда (Django)

```
POSTGRES_HOST=localhost
CELERY_BROKER_URL=amqp://monitoring:monitoring@localhost:5672//
EMAIL_HOST=localhost
EMAIL_PORT=1025
```

## Переход на одну базу

Раньше принятые события лежали в отдельной базе `monitoring_raw` (сервис `postgres-raw`, порт 5433), теперь всё в одной базе `monitoring`. Если стенд поднимался со старой схемой, нужно выполнить шаги ниже: Django уже считает миграции `processing` примененными к основной базе, хотя таблицы `processing_incomingevent` в ней нет, и без этого прием событий падает с ошибкой 500.

Без сохранения данных (проще всего):

```
cd infra
docker compose down -v --remove-orphans
docker volume ls                      # найти старый том, например vkr-infra_pgdata_raw
docker volume rm vkr-infra_pgdata_raw
docker compose up -d
cd ../backend
python manage.py migrate
python manage.py demo_reset
```

С сохранением данных основной базы (события из `monitoring_raw` при этом не переносятся):

```
cd backend
python manage.py migrate processing zero --fake
python manage.py migrate processing
```

Этот вариант подходит, только если таблицы `processing_incomingevent` в базе `monitoring` нет (проверить: `docker exec vkr-postgres psql -U monitoring -d monitoring -c '\dt processing*'`). Если она осталась от старой версии, используйте первый вариант. Старый контейнер `vkr-postgres-raw` удаляется командой `docker compose down --remove-orphans`, том — так же через `docker volume rm`.

## Полезные команды

- Остановить: `docker compose down` (данные сохраняются)
- Сбросить всё до нуля: `docker compose down -v`
- Логи сервиса: `docker compose logs -f rabbitmq`
- Зайти в базу: `docker exec -it vkr-postgres psql -U monitoring -d monitoring`
