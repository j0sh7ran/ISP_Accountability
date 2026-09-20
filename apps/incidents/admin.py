from django.contrib import admin

from .models import Event, EventEvidence, Incident


class EventEvidenceInline(admin.TabularInline):
    model = EventEvidence
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class EventInline(admin.TabularInline):
    model = Event
    extra = 0
    fields = ('type', 'start_time', 'end_time', 'severity', 'description')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ReadOnlyIncidentAdmin(admin.ModelAdmin):
    """Derived data, not hand-authored — no add/change form needed in the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Incident)
class IncidentAdmin(ReadOnlyIncidentAdmin):
    list_display = ('type', 'start_time', 'end_time', 'duration_seconds', 'severity', 'recovery_status')
    list_filter = ('type', 'severity', 'recovery_status')
    date_hierarchy = 'start_time'
    inlines = [EventInline]


@admin.register(Event)
class EventAdmin(ReadOnlyIncidentAdmin):
    list_display = ('type', 'start_time', 'end_time', 'severity', 'incident')
    list_filter = ('type', 'severity')
    date_hierarchy = 'start_time'
    inlines = [EventEvidenceInline]
