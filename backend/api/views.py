from rest_framework import viewsets
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (
    Department, Employee, BusinessService, ConfigurationItem,
    Incident, Event,
)
from .serializers import (
    DepartmentSerializer, PersonSerializer, ServiceSerializer,
    ResourceSerializer, IncidentSerializer, MonitoringEventSerializer,
)


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status': 'ok'})


class DepartmentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    # Меняем Person на Employee
    queryset = Employee.objects.select_related('department').all()
    serializer_class = PersonSerializer


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    # Меняем Service на BusinessService
    queryset = BusinessService.objects.select_related('department', 'owner').all()
    serializer_class = ServiceSerializer


class ResourceViewSet(viewsets.ReadOnlyModelViewSet):
    # Меняем Resource на ConfigurationItem, а services -> service_cis
    queryset = (
        ConfigurationItem.objects
        .select_related('owner', 'ci_class')
        .prefetch_related('service_cis', 'outgoing_relations')
    )
    serializer_class = ResourceSerializer


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = (
        Incident.objects
        .select_related('root_cause_ci', 'responsible', 'assignee', 'closed_by')
        .prefetch_related('incident_services', 'timeline')
    )
    serializer_class = IncidentSerializer

    @action(detail=True, methods=['get'])
    def events(self, request, pk=None):
        incident = self.get_object()
        # Связь теперь называется events (Event), а ресурс - ci
        events = incident.events.select_related('ci').all()
        serializer = MonitoringEventSerializer(events, many=True)
        return Response(serializer.data)


class MonitoringEventViewSet(viewsets.ReadOnlyModelViewSet):
    # Меняем MonitoringEvent на Event
    queryset = Event.objects.select_related('incident', 'ci').all()
    serializer_class = MonitoringEventSerializer
    filter_backends = []