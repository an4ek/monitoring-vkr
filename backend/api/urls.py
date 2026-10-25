from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    health, DepartmentViewSet, PersonViewSet, ServiceViewSet,
    ResourceViewSet, IncidentViewSet, MonitoringEventViewSet,
)

router = DefaultRouter()
router.register('departments', DepartmentViewSet, basename='department')
router.register('people', PersonViewSet, basename='person')
router.register('services', ServiceViewSet, basename='service')
router.register('resources', ResourceViewSet, basename='resource')
router.register('incidents', IncidentViewSet, basename='incident')
router.register('events', MonitoringEventViewSet, basename='event')

urlpatterns = [
    path('health/', health, name='health'),
    path('', include(router.urls)),
]