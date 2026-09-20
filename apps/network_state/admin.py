from django.contrib import admin

from .models import NetworkStateLog, StateMachineConfig


@admin.register(StateMachineConfig)
class StateMachineConfigAdmin(admin.ModelAdmin):
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
