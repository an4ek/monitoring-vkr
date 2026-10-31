"""Пользователи системы и их роли."""
from django.conf import settings
from django.db import models

from api.models import Employee


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Администратор'
        ENGINEER = 'engineer', 'Инженер'
        MANAGER = 'manager', 'Руководитель'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices)
    # Меняем Person на Employee
    person = models.OneToOneField(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name='profile',
        help_text='Сотрудник из каталога. Нужен инженеру и руководителю: от его имени берутся инциденты и подписки.',
    )

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'