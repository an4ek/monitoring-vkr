class RawEventRouter:
    """
    Направляет модели приложения processing в базу 'raw'.
    """
    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'processing':
            return 'raw'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'processing':
            return 'raw'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Разрешаем связи между объектами из разных баз (Django будет ругаться, но мы обходим)
        if obj1._state.db == obj2._state.db:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == 'processing':
            return db == 'raw'
        return db == 'default'