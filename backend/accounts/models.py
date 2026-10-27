"""Пользователи системы и их роли (диаграмма вариантов использования).

Учетная запись для входа — стандартный пользователь Django (логин и пароль).
К ней привязан профиль: роль и сотрудник из каталога, от имени которого
пользователь работает (чтобы в истории инцидента было видно, кто что сделал).
"""
from django.conf import settings
from django.db import models

from api.models import Person


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        ENGINEER = 'engineer', 'Инженер'
        MANAGER = 'manager', 'Руководитель'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices)
    person = models.OneToOneField(
        Person, null=True, blank=True, on_delete=models.SET_NULL, related_name='profile',
        help_text='Сотрудник из каталога. Нужен инженеру и руководителю: от его имени берутся инциденты и подписки.',
    )

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'
