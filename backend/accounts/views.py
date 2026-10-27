"""Вход, выход и «кто я».

Вход по сессии Django: после входа браузер хранит cookie сессии (недоступную
для JavaScript), а изменяющие запросы защищены CSRF-токеном.
"""
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import exceptions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


def _me(user):
    profile = getattr(user, 'profile', None)
    return {
        'username': user.username,
        'role': profile.role if profile else None,
        'role_label': profile.get_role_display() if profile else 'Без роли',
        'person_id': profile.person_id if profile else None,
        'full_name': (profile.person.full_name if profile and profile.person else user.get_full_name() or user.username),
    }


@api_view(['GET'])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def csrf(request):
    """Выдает браузеру CSRF-cookie, без которой не пройдет вход."""
    return Response({'status': 'ok'})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    # Вход тоже проверяем на CSRF, чтобы чужой сайт не мог войти от имени пользователя
    try:
        SessionAuthentication().enforce_csrf(request)
    except exceptions.PermissionDenied:
        return Response({'detail': 'Обновите страницу и попробуйте еще раз'}, status=status.HTTP_403_FORBIDDEN)
    user = authenticate(
        request,
        username=str(request.data.get('username', '')),
        password=str(request.data.get('password', '')),
    )
    if user is None or not user.is_active:
        return Response({'detail': 'Неверный логин или пароль'}, status=status.HTTP_400_BAD_REQUEST)
    if not hasattr(user, 'profile'):
        return Response({'detail': 'У пользователя не назначена роль'}, status=status.HTTP_403_FORBIDDEN)
    login(request, user)
    return Response(_me(user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(_me(request.user))
