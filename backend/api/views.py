from django.shortcuts import render

from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import api_view, action
from rest_framework.response import Response

from .models import (
    Department, Person, Service, Resource,
    Incident, MonitoringEvent,
)
from .serializers import (
    DepartmentSerializer, PersonSerializer, ServiceSerializer,
    ResourceSerializer, IncidentSerializer, MonitoringEventSerializer,
)


@api_view(['GET'])
def health(request):
    return Response({'status': 'ok'})


class DepartmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Person.objects.select_related('department').all()
    serializer_class = PersonSerializer


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.select_related('department', 'owner').all()
    serializer_class = ServiceSerializer


class ResourceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Resource.objects
        .select_related('owner')
        .prefetch_related('services', 'depends_on')
    )
    serializer_class = ResourceSerializer


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Incident.objects
        .select_related('root_cause', 'responsible')
        .prefetch_related('affected_services', 'history')
    )
    serializer_class = IncidentSerializer

    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        incident = self.get_object()
        events = incident.events.select_related('resource').all()
        serializer = MonitoringEventSerializer(events, many=True)
        return Response(serializer.data)


class MonitoringEventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MonitoringEvent.objects.select_related('incident', 'resource').all()
    serializer_class = MonitoringEventSerializer
    filter_backends = []