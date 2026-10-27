"""Проверки прав по ролям."""
from rest_framework.permissions import BasePermission


def role_of(user):
    profile = getattr(user, 'profile', None)
    return profile.role if profile else None


class HasRole(BasePermission):
    """Пропускает только пользователей с одной из перечисленных ролей.

    Использование: permission_classes = [HasRole.of('engineer')]
    """
    roles: tuple[str, ...] = ()
    message = 'Это действие недоступно для вашей роли'

    @classmethod
    def of(cls, *roles):
        return type(f'HasRole_{"_".join(roles)}', (cls,), {'roles': roles})

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and role_of(request.user) in self.roles)
