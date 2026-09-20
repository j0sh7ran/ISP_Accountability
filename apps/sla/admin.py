from django.contrib import admin

from apps.core.admin_csv import CSVImportExportMixin

from .models import SLAEvaluation, SLARule


@admin.register(SLARule)
class SLARuleAdmin(CSVImportExportMixin, admin.ModelAdmin):
    list_display = ('name', 'metric', 'operator', 'threshold', 'unit', 'severity', 'enabled')
    list_filter = ('metric', 'severity', 'enabled')
    search_fields = ('name', 'destination_filter')
    csv_fields = (
        'name', 'metric', 'operator', 'threshold', 'unit', 'min_duration_seconds',
        'measurement_window_seconds', 'protocol', 'destination_filter', 'time_period_filter',
        'severity', 'enabled',
    )
    csv_key_fields = ('name',)


@admin.register(SLAEvaluation)
class SLAEvaluationAdmin(admin.ModelAdmin):
    """Derived data, not hand-authored — no add/change form needed in the admin."""

    list_display = ('rule', 'status', 'observed_value', 'threshold_value', 'window_start', 'window_end', 'incident')
    list_filter = ('status', 'rule')
    date_hierarchy = 'window_end'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
