"""API, которое добавляет обработка событий.

  POST /api/events/zabbix/          — прием события от Zabbix
  POST /api/events/alertmanager/    — прием события от Prometheus (Alertmanager)
  POST /api/incidents/<id>/take/    — взять инцидент в работу (только инженер)
  POST /api/incidents/<id>/close/   — закрыть инцидент (только инженер)
  /api/subscriptions/               — свои подписки на сервисы (инженер, руководитель)
  POST /api/resources/<id>/owner/   — назначить ответственного за ресурс (только руководитель)
  POST /api/services/<id>/owner/    — назначить ответственного за сервис (только руководитель)
"""
import hmac

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, mixins, serializers, status, viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.permissions import HasRole

from api.models import Incident, IncidentHistoryItem, Person, Resource, Service
from api.serializers import IncidentSerializer, ResourceSerializer, ServiceSerializer

from .models import Subscription
from .normalize import InvalidEvent, from_alertmanager, from_zabbix
from .tasks import process_event


def _accept(request, normalizer):
    """Прием события: привести к единому виду, поставить задачу в очередь, сразу ответить.

    Сама обработка идет в обработчике (Celery), поэтому мониторинг не ждет.
    """
    # Сравнение за постоянное время, чтобы ключ нельзя было подобрать по времени ответа
    token = request.headers.get('X-Webhook-Token', '')
    if not hmac.compare_digest(token.encode(), settings.WEBHOOK_TOKEN.encode()):
        return Response({'detail': 'Неверный ключ'}, status=status.HTTP_403_FORBIDDEN)
    try:
        events = normalizer(request.data)
    except InvalidEvent as error:
        return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)
    for event in events:
        process_event.delay(event)
    return Response({'status': 'Принято', 'events': len(events)}, status=status.HTTP_202_ACCEPTED)


# Мониторинг входит не по логину, а по секретному ключу (проверка в _accept)
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def zabbix_webhook(request):
    return _accept(request, from_zabbix)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def alertmanager_webhook(request):
    return _accept(request, from_alertmanager)


# --- Разбор инцидента --------------------------------------------------------
# Брать в работу и закрывать может только инженер. Действие записывается
# от имени сотрудника, привязанного к его учетной записи.

class NoPerson(Exception):
    pass


def _person(request):
    person = request.user.profile.person
    if person is None:
        raise NoPerson
    return person


def _no_person():
    return Response(
        {'detail': 'К вашей учетной записи не привязан сотрудник. Обратитесь к администратору.'},
        status=status.HTTP_403_FORBIDDEN,
    )


def _history(incident, text):
    IncidentHistoryItem.objects.create(incident=incident, at=timezone.now(), text=text)


@api_view(['POST'])
@permission_classes([HasRole.of('engineer')])
def take_incident(request, pk):
    try:
        person = _person(request)
    except NoPerson:
        return _no_person()
    with transaction.atomic():
        incident = get_object_or_404(Incident.objects.select_for_update(), pk=pk)
        if incident.status != Incident.Status.OPEN:
            return Response({'detail': 'Взять в работу можно только открытый инцидент'}, status=status.HTTP_409_CONFLICT)
        incident.status = Incident.Status.IN_PROGRESS
        incident.assignee = person
        incident.save(update_fields=['status', 'assignee'])
        _history(incident, f'Взят в работу: {person.full_name}')
    return Response(IncidentSerializer(incident).data)


@api_view(['POST'])
@permission_classes([HasRole.of('engineer')])
def close_incident(request, pk):
    try:
        person = _person(request)
    except NoPerson:
        return _no_person()
    comment = str(request.data.get('comment', '')).strip()[:1000]
    with transaction.atomic():
        incident = get_object_or_404(Incident.objects.select_for_update(), pk=pk)
        if incident.status == Incident.Status.RESOLVED:
            return Response({'detail': 'Инцидент уже закрыт'}, status=status.HTTP_409_CONFLICT)
        incident.status = Incident.Status.RESOLVED
        incident.resolved_at = timezone.now()
        incident.closed_by = person
        if incident.assignee is None:
            incident.assignee = person
        incident.save(update_fields=['status', 'resolved_at', 'closed_by', 'assignee'])
        _history(incident, f'Закрыт вручную: {person.full_name}' + (f'. {comment}' if comment else ''))
    return Response(IncidentSerializer(incident).data)


# --- Подписки ----------------------------------------------------------------
# Инженер и руководитель видят и меняют только свои подписки.

class SubscriptionSerializer(serializers.ModelSerializer):
    person_id = serializers.PrimaryKeyRelatedField(source='person', read_only=True)
    service_id = serializers.PrimaryKeyRelatedField(source='service', queryset=Service.objects.all())

    class Meta:
        model = Subscription
        fields = ['id', 'person_id', 'service_id', 'created_at']
        read_only_fields = ['created_at']


class SubscriptionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin,
                          mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [HasRole.of('engineer', 'manager')]

    def get_queryset(self):
        return Subscription.objects.filter(person=self.request.user.profile.person)

    def perform_create(self, serializer):
        person = self.request.user.profile.person
        if person is None:
            raise exceptions.PermissionDenied('К вашей учетной записи не привязан сотрудник')
        if Subscription.objects.filter(person=person, service=serializer.validated_data['service']).exists():
            raise exceptions.ValidationError({'service_id': 'Вы уже подписаны на этот сервис'})
        serializer.save(person=person)


# --- Назначение ответственных ------------------------------------------------
# По диаграмме вариантов использования ответственных назначает только руководитель.
# Ответственный обязателен, поэтому снять его нельзя — только заменить.

def _assign_owner(request, model, serializer_class, pk):
    obj = get_object_or_404(model, pk=pk)
    # person_id может прийти не числом (строка, null) — тогда сотрудник не выбран
    try:
        person = Person.objects.filter(id=int(request.data.get('person_id'))).first()
    except (TypeError, ValueError):
        person = None
    if person is None:
        return Response({'detail': 'Выберите сотрудника'}, status=status.HTTP_400_BAD_REQUEST)
    obj.owner = person
    obj.save(update_fields=['owner'])
    return Response(serializer_class(obj).data)


@api_view(['POST'])
@permission_classes([HasRole.of('manager')])
def assign_resource_owner(request, pk):
    return _assign_owner(request, Resource, ResourceSerializer, pk)


@api_view(['POST'])
@permission_classes([HasRole.of('manager')])
def assign_service_owner(request, pk):
    return _assign_owner(request, Service, ServiceSerializer, pk)
