"""API, которое добавляет обработка событий.

  POST /api/events/zabbix/          — прием события от Zabbix
  POST /api/events/alertmanager/    — прием события от Prometheus (Alertmanager)
  POST /api/incidents/<id>/take/    — взять инцидент в работу
  POST /api/incidents/<id>/close/   — закрыть инцидент
  /api/subscriptions/               — подписки сотрудников на сервисы
"""
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response

from api.models import Incident, IncidentHistoryItem, Person, Service
from api.serializers import IncidentSerializer

from .models import Subscription
from .normalize import InvalidEvent, from_alertmanager, from_zabbix
from .tasks import process_event


def _accept(request, normalizer):
    """Прием события: привести к единому виду, поставить задачу в очередь, сразу ответить.

    Сама обработка идет в обработчике (Celery), поэтому мониторинг не ждет.
    """
    if settings.WEBHOOK_TOKEN and request.headers.get('X-Webhook-Token') != settings.WEBHOOK_TOKEN:
        return Response({'detail': 'Неверный ключ'}, status=status.HTTP_403_FORBIDDEN)
    try:
        events = normalizer(request.data)
    except InvalidEvent as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
    for event in events:
        process_event.delay(event)
    return Response({'status': 'Принято', 'events': len(events)}, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@authentication_classes([])
def zabbix_webhook(request):
    return _accept(request, from_zabbix)


@api_view(['POST'])
@authentication_classes([])
def alertmanager_webhook(request):
    return _accept(request, from_alertmanager)


# --- Разбор инцидента --------------------------------------------------------
# Пока нет входа в систему, кто нажал кнопку, передается в person_id.
# Проверка роли («только инженер») появится вместе с авторизацией.

def _person(request):
    return get_object_or_404(Person, id=request.data.get('person_id'))


def _history(incident, text):
    IncidentHistoryItem.objects.create(incident=incident, at=timezone.now(), text=text)


@api_view(['POST'])
@authentication_classes([])
def take_incident(request, pk):
    with transaction.atomic():
        incident = get_object_or_404(Incident.objects.select_for_update(), pk=pk)
        if incident.status != Incident.Status.OPEN:
            return Response({'detail': 'Взять в работу можно только открытый инцидент'}, status=status.HTTP_409_CONFLICT)
        person = _person(request)
        incident.status = Incident.Status.IN_PROGRESS
        incident.save(update_fields=['status'])
        _history(incident, f'Взят в работу: {person.full_name}')
    return Response(IncidentSerializer(incident).data)


@api_view(['POST'])
@authentication_classes([])
def close_incident(request, pk):
    with transaction.atomic():
        incident = get_object_or_404(Incident.objects.select_for_update(), pk=pk)
        if incident.status == Incident.Status.RESOLVED:
            return Response({'detail': 'Инцидент уже закрыт'}, status=status.HTTP_409_CONFLICT)
        person = _person(request)
        comment = str(request.data.get('comment', '')).strip()
        incident.status = Incident.Status.RESOLVED
        incident.resolved_at = timezone.now()
        incident.save(update_fields=['status', 'resolved_at'])
        _history(incident, f'Закрыт вручную: {person.full_name}' + (f'. {comment}' if comment else ''))
    return Response(IncidentSerializer(incident).data)


# --- Подписки ----------------------------------------------------------------

class SubscriptionSerializer(serializers.ModelSerializer):
    person_id = serializers.PrimaryKeyRelatedField(source='person', queryset=Person.objects.all())
    service_id = serializers.PrimaryKeyRelatedField(source='service', queryset=Service.objects.all())

    class Meta:
        model = Subscription
        fields = ['id', 'person_id', 'service_id', 'created_at']
        read_only_fields = ['created_at']


class SubscriptionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                          mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Subscription.objects.all()
    authentication_classes = []
    serializer_class = SubscriptionSerializer
