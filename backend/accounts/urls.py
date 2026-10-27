from django.urls import path

from .views import csrf, login_view, logout_view, me

urlpatterns = [
    path('auth/csrf/', csrf),
    path('auth/login/', login_view),
    path('auth/logout/', logout_view),
    path('auth/me/', me),
]
