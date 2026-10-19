# Инфраструктура для разработки

PostgreSQL, RabbitMQ, Redis и Mailpit в Docker.

## Запуск

```
cd infra
cp .env.example .env
docker compose up -d
docker compose ps
```

Все четыре сервиса должны быть в статусе `running` (у PostgreSQL и RabbitMQ — `healthy`).

## Что где

| Сервис | Адрес | Зачем |
|---|---|---|
| PostgreSQL | `localhost:5432` | База данных системы |
| RabbitMQ | `localhost:5672`, панель `http://localhost:15672` | Брокер для Celery и очередь событий |
| Redis | `localhost:6379` | Кэш |
| Mailpit | SMTP `localhost:1025`, веб `http://localhost:8025` | Перехватывает письма: всё, что отправит система, видно в веб-интерфейсе, наружу ничего не уходит |

Логин и пароль везде по умолчанию `monitoring` / `monitoring` (меняются в `.env`).

## Настройки для бэкенда (Django)

```
DATABASE_URL=postgres://monitoring:monitoring@localhost:5432/monitoring
CELERY_BROKER_URL=amqp://monitoring:monitoring@localhost:5672//
REDIS_URL=redis://localhost:6379/0
EMAIL_HOST=localhost
EMAIL_PORT=1025
```

## Полезные команды

- Остановить: `docker compose down` (данные сохраняются)
- Сбросить всё до нуля: `docker compose down -v`
- Логи сервиса: `docker compose logs -f rabbitmq`
- Зайти в базу: `docker exec -it vkr-postgres psql -U monitoring -d monitoring`
