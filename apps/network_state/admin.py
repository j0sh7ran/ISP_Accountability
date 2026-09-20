from django.contrib import admin

from apps.core.admin_csv import CSVImportExportMixin

from .models import NetworkStateLog, StateMachineConfig


@admin.register(StateMachineConfig)
class StateMachineConfigAdmin(CSVImportExportMixin, admin.ModelAdmin):
    csv_fields = (
        'consecutive_failures_for_degraded', 'consecutive_failures_for_offline',
        'min_independent_targets_failing', 'recovery_confirmation_successes',
        'micro_outage_threshold_seconds',
    )
    csv_singleton = True  # exactly one row is ever expected — always update pk=1, never create more.

    def has_add_permission(self, request):
        # Singleton — only the one row created by get_solo() should ever exist.
        return not StateMachineConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NetworkStateLog)
class NetworkStateLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'previous_state', 'new_state', 'reason')
    list_filter = ('previous_state', 'new_state')
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
