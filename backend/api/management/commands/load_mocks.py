import uuid
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from api.models import (
    Department, Employee, CIClass, CIRelationshipType, ConfigurationItem,
    CIRelationship, BusinessService, ServiceCI, Incident, IncidentTimeline, IncidentService,
    MonitoringSystem, Subscription
)

class Command(BaseCommand):
    help = 'Загружает тестовые данные в CMDB'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Очистка старых данных...')
        IncidentService.objects.all().delete()
        IncidentTimeline.objects.all().delete()
        Incident.objects.all().delete()
        ServiceCI.objects.all().delete()
        BusinessService.objects.all().delete()
        CIRelationship.objects.all().delete()
        ConfigurationItem.objects.all().delete()
        CIRelationshipType.objects.all().delete()
        CIClass.objects.all().delete()
        Employee.objects.all().delete()
        Department.objects.all().delete()

        self.stdout.write('Создание систем мониторинга...')
        mon_zabbix = MonitoringSystem.objects.create(name='Zabbix', system_type='zabbix', ingest_method='webhook')
        mon_prom = MonitoringSystem.objects.create(name='Prometheus', system_type='prometheus', ingest_method='webhook')
        self.stdout.write('Создание отделов и сотрудников...')
        dep_infra = Department.objects.create(name='ИТ-инфраструктура', code='infra')
        dep_dev = Department.objects.create(name='Разработка', code='dev')
        dep_sales = Department.objects.create(name='Отдел продаж', code='sales')

        emp_ivanov = Employee.objects.create(login='ivanov', full_name='Иванов Сергей', email='ivanov@example.local', department=dep_infra, mattermost='@ivanov')
        emp_petrova = Employee.objects.create(login='petrova', full_name='Петрова Мария', email='petrova@example.local', department=dep_infra, mattermost='@petrova')
        emp_smirnov = Employee.objects.create(login='smirnov', full_name='Смирнов Алексей', email='smirnov@example.local', department=dep_dev, mattermost='@smirnov')
        emp_orlova = Employee.objects.create(login='orlova', full_name='Орлова Елена', email='orlova@example.local', department=dep_dev, mattermost='@orlova')

        self.stdout.write('Создание классов объектов и типов связей...')
        class_server = CIClass.objects.create(code='server', name='Сервер')
        class_db = CIClass.objects.create(code='database', name='База данных')
        class_app = CIClass.objects.create(code='application', name='Приложение')
        class_net = CIClass.objects.create(code='network', name='Сеть')
        class_queue = CIClass.objects.create(code='queue', name='Очередь')
        class_cache = CIClass.objects.create(code='cache', name='Кэш')

        rel_depends = CIRelationshipType.objects.create(code='depends_on', name='Зависит от', propagates_failure=True)

        self.stdout.write('Создание ресурсов (CI)...')
        # Словарь для удобного связывания по имени
        ci = {}
        
        def add_ci(name, ci_class, desc, owner):
            c = ConfigurationItem.objects.create(
                name=name, ci_class=ci_class, environment='prod',
                department=dep_infra, owner=owner, attributes={'description': desc}
            )
            ci[name] = c
            return c

        add_ci('sw-core-01', class_net, 'Центральный коммутатор', emp_ivanov)
        add_ci('lb-01', class_app, 'Балансировщик Nginx', emp_ivanov)
        add_ci('web-01', class_server, 'Веб-сервер сайта', emp_ivanov)
        add_ci('app-site', class_app, 'Приложение сайта', emp_smirnov)
        add_ci('app-crm', class_app, 'Приложение CRM', emp_orlova)
        add_ci('db-01', class_db, 'PostgreSQL сайта', emp_ivanov)
        add_ci('db-02', class_db, 'PostgreSQL CRM', emp_ivanov)
        add_ci('mq-01', class_queue, 'RabbitMQ для CRM', emp_ivanov)
        add_ci('srv-1c', class_server, 'Сервер 1С', emp_ivanov)
        add_ci('db-1c', class_db, 'PostgreSQL для 1С', emp_ivanov)
        add_ci('mail-01', class_server, 'Почтовый сервер', emp_petrova)

        self.stdout.write('Создание графа зависимостей...')
        # В новой схеме source зависит от target
        # app-site зависит от web-01 и db-01
        CIRelationship.objects.create(source_ci=ci['app-site'], target_ci=ci['web-01'], relationship_type=rel_depends)
        CIRelationship.objects.create(source_ci=ci['app-site'], target_ci=ci['db-01'], relationship_type=rel_depends)
        # web-01 зависит от sw-core-01
        CIRelationship.objects.create(source_ci=ci['web-01'], target_ci=ci['sw-core-01'], relationship_type=rel_depends)
        CIRelationship.objects.create(source_ci=ci['db-01'], target_ci=ci['sw-core-01'], relationship_type=rel_depends)
        
        # app-crm зависит от db-02 и mq-01
        CIRelationship.objects.create(source_ci=ci['app-crm'], target_ci=ci['db-02'], relationship_type=rel_depends)
        CIRelationship.objects.create(source_ci=ci['app-crm'], target_ci=ci['mq-01'], relationship_type=rel_depends)
        CIRelationship.objects.create(source_ci=ci['db-02'], target_ci=ci['sw-core-01'], relationship_type=rel_depends)

        # srv-1c зависит от db-1c
        CIRelationship.objects.create(source_ci=ci['srv-1c'], target_ci=ci['db-1c'], relationship_type=rel_depends)
        CIRelationship.objects.create(source_ci=ci['srv-1c'], target_ci=ci['sw-core-01'], relationship_type=rel_depends)

        self.stdout.write('Создание бизнес-сервисов...')
        s_site = BusinessService.objects.create(name='Корпоративный сайт', description='Сайт компании и форма заявок', service_type='web', department=dep_sales, owner=emp_smirnov, current_status='ok')
        s_crm = BusinessService.objects.create(name='CRM', description='Учёт клиентов и сделок', service_type='web', department=dep_sales, owner=emp_orlova, current_status='ok')
        s_1c = BusinessService.objects.create(name='1С: Бухгалтерия', description='Система бухгалтерского учета', service_type='erp', department=dep_infra, owner=emp_ivanov, current_status='ok')
        s_mail = BusinessService.objects.create(name='Корпоративная почта', description='Корпоративный email-сервис', service_type='comm', department=dep_infra, owner=emp_petrova, current_status='ok')

        self.stdout.write('Привязка ресурсов к сервисам...')
        # Сайт
        ServiceCI.objects.create(service=s_site, ci=ci['app-site'])
        ServiceCI.objects.create(service=s_site, ci=ci['web-01'])
        ServiceCI.objects.create(service=s_site, ci=ci['db-01'])
        # CRM
        ServiceCI.objects.create(service=s_crm, ci=ci['app-crm'])
        ServiceCI.objects.create(service=s_crm, ci=ci['db-02'])
        # 1C
        ServiceCI.objects.create(service=s_1c, ci=ci['srv-1c'])
        ServiceCI.objects.create(service=s_1c, ci=ci['db-1c'])
        # Почта
        ServiceCI.objects.create(service=s_mail, ci=ci['mail-01'])

        self.stdout.write('Создание подписок...')
        Subscription.objects.create(person=emp_petrova, service=s_site)
        Subscription.objects.create(person=emp_orlova, service=s_1c)

        self.stdout.write('Создание тестового инцидента...')
        inc = Incident.objects.create(
            title='Недоступны CRM и личный кабинет',
            status='open',
            severity='critical',
            root_cause_ci=ci['db-02'],
            responsible=emp_ivanov,
            started_at=timezone.now() - timedelta(minutes=15)
        )
        IncidentService.objects.create(incident=inc, service=s_crm, impact_level='high')
        IncidentTimeline.objects.create(incident=inc, entry_type='system', text='Инцидент создан по событию от Zabbix')

        self.stdout.write(self.style.SUCCESS('Тестовые данные CMDB успешно загружены!'))