from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    SubscriptionViewSet, alertmanager_webhook, assign_resource_owner, assign_service_owner,
    close_incident, take_incident, zabbix_webhook,
)

router = DefaultRouter()
router.register('subscriptions', SubscriptionViewSet, basename='subscription')

urlpatterns = [
    path('events/zabbix/', zabbix_webhook, name='zabbix-webhook'),
    path('events/alertmanager/', alertmanager_webhook, name='alertmanager-webhook'),
    path('incidents/<int:pk>/take/', take_incident, name='incident-take'),
    path('incidents/<int:pk>/close/', close_incident, name='incident-close'),
    path('resources/<int:pk>/owner/', assign_resource_owner, name='resource-owner'),
    path('services/<int:pk>/owner/', assign_service_owner, name='service-owner'),
    path('', include(router.urls)),
]
