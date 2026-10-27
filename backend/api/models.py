from django.db import models

class Department(models.Model):
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Person(models.Model):
    full_name = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='people')
    email = models.EmailField()
    mattermost = models.CharField(max_length=100)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.full_name


class Service(models.Model):
    class Status(models.TextChoices):
        OK = 'ok', 'Работает'
        DEGRADED = 'degraded', 'С проблемами'
        DOWN = 'down', 'Не работает'

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='services')
    owner = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='owned_services')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OK)
    slo_target = models.FloatField()
    availability = models.FloatField()

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Resource(models.Model):
    class Type(models.TextChoices):
        SERVER = 'server', 'Сервер'
        DATABASE = 'database', 'База данных'
        APPLICATION = 'application', 'Приложение'
        NETWORK = 'network', 'Сеть'
        QUEUE = 'queue', 'Очередь'
        CACHE = 'cache', 'Кэш'

    class Environment(models.TextChoices):
        PROD = 'prod', 'prod'
        TEST = 'test', 'test'

    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=Type.choices)
    environment = models.CharField(max_length=10, choices=Environment.choices, default=Environment.PROD)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='owned_resources')
    services = models.ManyToManyField(Service, blank=True, related_name='resources')
    depends_on = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='dependents')
    runbook_url = models.URLField(blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name


class Incident(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Открыт'
        IN_PROGRESS = 'in_progress', 'В работе'
        RESOLVED = 'resolved', 'Закрыт'

    class Severity(models.TextChoices):
        CRITICAL = 'critical', 'Критично'
        WARNING = 'warning', 'Предупреждение'
        INFO = 'info', 'Информация'

    title = models.CharField(max_length=300)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    root_cause = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='incidents_as_root_cause')
    affected_services = models.ManyToManyField(Service, blank=True, related_name='incidents')
    responsible = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='responsible_incidents')
    # Кто взял инцидент в работу и кто закрыл вручную (пусто, если закрыт автоматически)
    assignee = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_incidents')
    closed_by = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name='closed_incidents')
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'№{self.pk}. {self.title}'


class IncidentHistoryItem(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='history')
    at = models.DateTimeField()
    text = models.TextField()

    class Meta:
        ordering = ['at']


class MonitoringEvent(models.Model):
    class Source(models.TextChoices):
        ZABBIX = 'zabbix', 'Zabbix'
        PROMETHEUS = 'prometheus', 'Prometheus'

    class Severity(models.TextChoices):
        CRITICAL = 'critical', 'Критично'
        WARNING = 'warning', 'Предупреждение'
        INFO = 'info', 'Информация'

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='events')
    source = models.CharField(max_length=20, choices=Source.choices)
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name='events')
    title = models.CharField(max_length=300)
    severity = models.CharField(max_length=20, choices=Severity.choices)
    received_at = models.DateTimeField()

    class Meta:
        ordering = ['received_at']

    def __str__(self):
        return self.title