from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Derived data, not hand-authored — no add/change form needed in the admin."""

    list_display = ('type', 'format', 'incident', 'generated_at', 'period_start', 'period_end')
    list_filter = ('type', 'format')
    date_hierarchy = 'generated_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
