"""Управление пользователями и ролями — в админке Django (/admin/), для администратора."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Роль и сотрудник'


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ['username', 'get_role', 'is_active']

    @admin.display(description='Роль')
    def get_role(self, user):
        return user.profile.get_role_display() if hasattr(user, 'profile') else '—'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
