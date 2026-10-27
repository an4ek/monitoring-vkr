# Подключаем Celery при старте Django, чтобы задачи можно было ставить в очередь.
from .celery import app as celery_app

__all__ = ('celery_app',)
