import uuid
from django.db import models
from django.contrib.auth.models import User


class Department(models.Model):
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    ldap_dn = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Location(models.Model):
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    location_type = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Employee(models.Model):
    ldap_guid = models.UUIDField(null=True, blank=True, unique=True)
    login = models.CharField(max_length=100, unique=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    manager = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='subordinates')
    is_active = models.BooleanField(default=True)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='employee')
    mattermost = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.full_name


class SupportGroup(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SupportGroupMember(models.Model):
    support_group = models.ForeignKey(SupportGroup, on_delete=models.CASCADE, related_name='members')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    member_role = models.CharField(max_length=20, default='member')

    class Meta:
        unique_together = ('support_group', 'employee')


class ResponsibilityZone(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL)
    support_group = models.ForeignKey(SupportGroup, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CIClass(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    attribute_schema = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.name


class ConfigurationItem(models.Model):
    name = models.CharField(max_length=200)
    ci_class = models.ForeignKey(CIClass, on_delete=models.PROTECT, related_name='items')
    environment = models.CharField(max_length=10)
    lifecycle_status = models.CharField(max_length=20, default='active')
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    zone = models.ForeignKey(ResponsibilityZone, null=True, blank=True, on_delete=models.SET_NULL)
    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name='owned_items')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    runbook_url = models.URLField(max_length=500, blank=True)
    attributes = models.JSONField(default=dict)
    discovery_source = models.CharField(max_length=20, default='manual')
    created_at = models.DateTimeField(auto_now_add=True)
    criticality = models.SmallIntegerField(default=3)

    class Meta:
        unique_together = ('name', 'environment')
        ordering = ['id']

    def __str__(self):
        return self.name


class CIRelationshipType(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    propagates_failure = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class CIRelationship(models.Model):
    source_ci = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name='outgoing_relations')
    target_ci = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name='incoming_relations')
    relationship_type = models.ForeignKey(CIRelationshipType, on_delete=models.PROTECT)

    class Meta:
        unique_together = ('source_ci', 'target_ci', 'relationship_type')


class BusinessService(models.Model):
    name = models.CharField(max_length=200)
    service_type = models.CharField(max_length=20)
    department = models.ForeignKey(Department, on_delete=models.PROTECT)
    owner = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='owned_services')
    slo_target = models.DecimalField(max_digits=6, decimal_places=3, default=99.9)
    current_status = models.CharField(max_length=20, default='unknown')
    status_updated_at = models.DateTimeField(null=True, blank=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    criticality = models.SmallIntegerField(default=3)

    def __str__(self):
        return self.name


class ServiceCI(models.Model):
    service = models.ForeignKey(BusinessService, on_delete=models.CASCADE, related_name='service_cis')
    ci = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name='service_cis')
    ci_role = models.CharField(max_length=20, default='core')

    class Meta:
        unique_together = ('service', 'ci')


class MonitoringSystem(models.Model):
    name = models.CharField(max_length=100, unique=True)
    system_type = models.CharField(max_length=30)
    base_url = models.CharField(max_length=300, blank=True)
    ingest_method = models.CharField(max_length=10)
    webhook_secret_hash = models.CharField(max_length=128, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Event(models.Model):
    monitoring_system = models.ForeignKey(MonitoringSystem, on_delete=models.PROTECT)
    ci = models.ForeignKey(ConfigurationItem, null=True, blank=True, on_delete=models.SET_NULL)
    incident = models.ForeignKey('Incident', null=True, blank=True, on_delete=models.SET_NULL, related_name='events')
    fingerprint = models.CharField(max_length=64)
    title = models.CharField(max_length=500)
    severity = models.CharField(max_length=10)
    status = models.CharField(max_length=10)
    labels = models.JSONField(null=True, blank=True)
    event_time = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    dedup_count = models.IntegerField(default=1)
    received_at = models.DateTimeField(auto_now_add=True)
    raw_payload = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']


class Incident(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Открыт'
        IN_PROGRESS = 'in_progress', 'В работе'
        RESOLVED = 'resolved', 'Закрыт'

    class Severity(models.TextChoices):
        CRITICAL = 'critical', 'Критично'
        WARNING = 'warning', 'Предупреждение'
        INFO = 'info', 'Информация'

    number = models.CharField(max_length=20, unique=True, blank=True)
    title = models.CharField(max_length=500)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    root_cause_ci = models.ForeignKey(ConfigurationItem, null=True, blank=True, on_delete=models.SET_NULL, related_name='root_cause_incidents')
    responsible = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL)
    assigned_group = models.ForeignKey(SupportGroup, null=True, blank=True, on_delete=models.SET_NULL)
    zone = models.ForeignKey(ResponsibilityZone, null=True, blank=True, on_delete=models.SET_NULL)
    events_count = models.IntegerField(default=1)
    started_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    
    # Для UI и ролей из старой ветки
    assignee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_incidents')
    closed_by = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name='closed_incidents')

    class Meta:
        ordering = ['-started_at']

    def save(self, *args, **kwargs):
        if not self.number:
            import uuid
            self.number = f'INC-{uuid.uuid4().hex[:6].upper()}'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'№{self.number}. {self.title}'


class IncidentService(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='incident_services')
    service = models.ForeignKey(BusinessService, on_delete=models.CASCADE)
    impact_level = models.CharField(max_length=10)

    class Meta:
        unique_together = ('incident', 'service')


class IncidentTimeline(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='timeline')
    entry_type = models.CharField(max_length=25)
    text = models.TextField()
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']