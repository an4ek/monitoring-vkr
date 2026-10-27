from rest_framework import serializers
from .models import (
    Department, Person, Service, Resource,
    Incident, IncidentHistoryItem, MonitoringEvent,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name']


class PersonSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField(source='department.id', read_only=True)

    class Meta:
        model = Person
        fields = ['id', 'full_name', 'department_id', 'email', 'mattermost']


class ServiceSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField(source='department.id', read_only=True)
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)

    class Meta:
        model = Service
        fields = [
            'id', 'name', 'description', 'department_id', 'owner_id',
            'status', 'slo_target', 'availability',
        ]


class ResourceSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source='owner.id', read_only=True)
    service_ids = serializers.PrimaryKeyRelatedField(
        source='services', many=True, read_only=True,
    )
    depends_on = serializers.PrimaryKeyRelatedField(
        many=True, read_only=True,
    )

    class Meta:
        model = Resource
        fields = [
            'id', 'name', 'type', 'environment', 'description',
            'owner_id', 'service_ids', 'depends_on', 'runbook_url',
        ]


class IncidentHistoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = IncidentHistoryItem
        fields = ['at', 'text']


class IncidentSerializer(serializers.ModelSerializer):
    root_cause_id = serializers.IntegerField(source='root_cause.id', read_only=True)
    affected_service_ids = serializers.PrimaryKeyRelatedField(
        source='affected_services', many=True, read_only=True,
    )
    responsible_id = serializers.IntegerField(source='responsible.id', read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(source='assignee', read_only=True)
    closed_by_id = serializers.PrimaryKeyRelatedField(source='closed_by', read_only=True)
    history = IncidentHistoryItemSerializer(many=True, read_only=True)

    class Meta:
        model = Incident
        fields = [
            'id', 'title', 'status', 'severity',
            'root_cause_id', 'affected_service_ids', 'responsible_id',
            'assignee_id', 'closed_by_id', 'started_at', 'resolved_at', 'history',
        ]


class MonitoringEventSerializer(serializers.ModelSerializer):
    incident_id = serializers.IntegerField(source='incident.id', read_only=True)
    resource_id = serializers.IntegerField(source='resource.id', read_only=True)

    class Meta:
        model = MonitoringEvent
        fields = [
            'id', 'incident_id', 'source', 'resource_id',
            'title', 'severity', 'received_at',
        ]