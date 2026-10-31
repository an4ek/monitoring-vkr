from rest_framework import serializers
from .models import (
    Department, Employee, BusinessService, ConfigurationItem,
    Incident, IncidentTimeline, Event,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name']


class PersonSerializer(serializers.ModelSerializer):
    # Фронтенд ждет department_id, поэтому делаем source='department.id'
    department_id = serializers.IntegerField(source='department.id', read_only=True)

    class Meta:
        model = Employee
        fields = ['id', 'full_name', 'department_id', 'email', 'mattermost']


class ServiceSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField(source='department.id', read_only=True)
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    
    # Фронтенд ждет status, slo_target, availability. 
    # В новой схеме поле называется current_status, адаптируем.
    status = serializers.CharField(source='current_status', read_only=True)
    availability = serializers.FloatField(source='slo_target', read_only=True) # Заглушка для UI

    class Meta:
        model = BusinessService
        fields = [
            'id', 'name', 'department_id', 'owner_id',
            'status', 'slo_target', 'availability',
        ]


class ResourceSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    type = serializers.CharField(source='ci_class.code', read_only=True)
    
    # Вычисляем сервисы, к которым привязан CI
    service_ids = serializers.SerializerMethodField()
    # Вычисляем зависимости из таблицы CIRelationship
    depends_on = serializers.SerializerMethodField()
    
    description = serializers.CharField(source='attributes.description', read_only=True, default='')

    class Meta:
        model = ConfigurationItem
        fields = [
            'id', 'name', 'type', 'environment', 'description',
            'owner_id', 'service_ids', 'depends_on', 'runbook_url',
        ]

    def get_service_ids(self, obj):
        return list(obj.service_cis.values_list('service_id', flat=True))

    def get_depends_on(self, obj):
        # Ищем связи, где source_ci - это наш ресурс, и тип связи передает сбой
        relations = obj.outgoing_relations.filter(relationship_type__propagates_failure=True)
        return list(relations.values_list('target_ci_id', flat=True))


class IncidentTimelineSerializer(serializers.ModelSerializer):
    at = serializers.DateTimeField(source='created_at', read_only=True)
    
    class Meta:
        model = IncidentTimeline
        fields = ['at', 'text']


class IncidentSerializer(serializers.ModelSerializer):
    root_cause_id = serializers.IntegerField(source='root_cause_ci.id', read_only=True)
    responsible_id = serializers.IntegerField(source='responsible.id', read_only=True)
    
    assignee_id = serializers.PrimaryKeyRelatedField(source='assignee', read_only=True)
    closed_by_id = serializers.PrimaryKeyRelatedField(source='closed_by', read_only=True)
    
    # Затронутые сервисы
    affected_service_ids = serializers.SerializerMethodField()
    
    # История теперь называется timeline, но фронт ждет history
    history = IncidentTimelineSerializer(source='timeline', many=True, read_only=True)

    class Meta:
        model = Incident
        fields = [
            'id', 'title', 'status', 'severity',
            'root_cause_id', 'affected_service_ids', 'responsible_id',
            'assignee_id', 'closed_by_id', 'started_at', 'resolved_at', 'history',
        ]

    def get_affected_service_ids(self, obj):
        return list(obj.incident_services.values_list('service_id', flat=True))


class MonitoringEventSerializer(serializers.ModelSerializer):
    incident_id = serializers.IntegerField(source='incident.id', read_only=True)
    resource_id = serializers.IntegerField(source='ci.id', read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 'incident_id', 'source', 'resource_id',
            'title', 'severity', 'received_at',
        ]