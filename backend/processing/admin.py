from django.contrib import admin

from .models import IncomingEvent, Notification, ResourceState, Subscription

admin.site.register([IncomingEvent, Notification, ResourceState, Subscription])
