from django.contrib import admin
from .models import IncomingEvent

@admin.register(IncomingEvent)
class IncomingEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'source', 'resource_name', 'status', 'received_at')
    list_filter = ('source', 'status')
    search_fields = ('resource_name', 'title')