from django.contrib import admin

from .models import MeasurementCategory, OnDemandTestRequest, RetentionPolicy, ScheduleConfig, Target


@admin.register(Target)
class TargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'address', 'port', 'address_family', 'protocol', 'enabled')
    list_filter = ('category', 'address_family', 'protocol', 'enabled')
    search_fields = ('name', 'address')


@admin.register(ScheduleConfig)
class ScheduleConfigAdmin(admin.ModelAdmin):
    list_display = ('task_type', 'interval_seconds', 'enabled', 'last_run')
    list_filter = ('enabled',)


@admin.register(RetentionPolicy)
class RetentionPolicyAdmin(admin.ModelAdmin):
    list_display = ('data_type', 'raw_retention_days', 'aggregate_retention_days')


@admin.register(OnDemandTestRequest)
class OnDemandTestRequestAdmin(admin.ModelAdmin):
    """Add a row here (task_type=throughput/bufferbloat) to trigger an on-demand test manually.

    Only these two task types are ever polled for pending requests by the worker (see
    apps/worker/jobs.py's ON_DEMAND_TASK_TYPES) — every other MeasurementCategory is periodic-only,
    controlled via ScheduleConfig, so the dropdown here is restricted to avoid creating inert rows.
    """

    list_display = ('task_type', 'status', 'requested_at', 'started_at', 'completed_at')
    list_filter = ('task_type', 'status')
    readonly_fields = ('started_at', 'completed_at', 'status')
    ON_DEMAND_CHOICES = [MeasurementCategory.THROUGHPUT, MeasurementCategory.BUFFERBLOAT]

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'task_type':
            kwargs['choices'] = [c for c in db_field.choices if c[0] in self.ON_DEMAND_CHOICES]
        return super().formfield_for_choice_field(db_field, request, **kwargs)
