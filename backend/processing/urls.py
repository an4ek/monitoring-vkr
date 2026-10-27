from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SubscriptionViewSet, alertmanager_webhook, close_incident, take_incident, zabbix_webhook

router = DefaultRouter()
router.register('subscriptions', SubscriptionViewSet, basename='subscription')

urlpatterns = [
    path('events/zabbix/', zabbix_webhook, name='zabbix-webhook'),
    path('events/alertmanager/', alertmanager_webhook, name='alertmanager-webhook'),
    path('incidents/<int:pk>/take/', take_incident, name='incident-take'),
    path('incidents/<int:pk>/close/', close_incident, name='incident-close'),
    path('', include(router.urls)),
]
