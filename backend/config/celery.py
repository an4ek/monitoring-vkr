# Настройка Celery: фоновый обработчик событий и оповещений.
# Задачи кладутся в очередь RabbitMQ, обработчик забирает их и выполняет.
# Запуск обработчика: celery -A config worker -l info
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')
# Все настройки Celery берутся из settings.py, из переменных с префиксом CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')
# Задачи ищутся в файлах tasks.py всех приложений
app.autodiscover_tasks()
