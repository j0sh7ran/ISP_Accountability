from django.contrib import admin

from .models import (
    BufferbloatTest,
    DailyAggregate,
    DNSMeasurement,
    HourlyAggregate,
    HTTPMeasurement,
    ICMPMeasurement,
    InterfaceMetric,
    MTUTestResult,
    RouteChangeEvent,
    RouteHop,
    RouteTestRun,
    TCPMeasurement,
    ThroughputMeasurement,
)


class ReadOnlyMeasurementAdmin(admin.ModelAdmin):
    """Collected data, not hand-authored — no add/change form needed in the admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ICMPMeasurement)
class ICMPMeasurementAdmin(ReadOnlyMeasurementAdmin):
    list_display = (
        'target', 'timestamp', 'address_family', 'sent', 'received', 'loss_pct', 'avg_rtt_ms', 'error',
    )
    list_filter = ('address_family', 'target')
    date_hierarchy = 'timestamp'


@admin.register(DNSMeasurement)
class DNSMeasurementAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('target', 'timestamp', 'query_name', 'result_type', 'resolution_time_ms', 'resolved_ip')
    list_filter = ('result_type', 'target')
    date_hierarchy = 'timestamp'


@admin.register(HTTPMeasurement)
class HTTPMeasurementAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('target', 'timestamp', 'status_code', 'total_time_ms', 'ttfb_ms', 'error_type')
    list_filter = ('target',)
    date_hierarchy = 'timestamp'


@admin.register(TCPMeasurement)
class TCPMeasurementAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('target', 'timestamp', 'port', 'success', 'connect_time_ms', 'error_type')
    list_filter = ('target', 'success')
    date_hierarchy = 'timestamp'


@admin.register(InterfaceMetric)
class InterfaceMetricAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('interface_name', 'timestamp', 'state', 'link_speed_mbps', 'bytes_sent', 'bytes_received')
    list_filter = ('interface_name', 'state')
    date_hierarchy = 'timestamp'


class RouteHopInline(admin.TabularInline):
    model = RouteHop
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RouteTestRun)
class RouteTestRunAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('target', 'timestamp', 'address_family')
    list_filter = ('target',)
    date_hierarchy = 'timestamp'
    inlines = [RouteHopInline]


@admin.register(RouteChangeEvent)
class RouteChangeEventAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('target', 'timestamp', 'hop_count_before', 'hop_count_after', 'first_hop_changed')
    list_filter = ('target', 'first_hop_changed')
    date_hierarchy = 'timestamp'


@admin.register(MTUTestResult)
class MTUTestResultAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('target', 'timestamp', 'largest_successful_size', 'failure_threshold', 'df_behavior')
    list_filter = ('target',)
    date_hierarchy = 'timestamp'


@admin.register(ThroughputMeasurement)
class ThroughputMeasurementAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('timestamp', 'test_type', 'mbps_down', 'mbps_up', 'endpoint', 'error')
    list_filter = ('test_type',)
    date_hierarchy = 'timestamp'


@admin.register(BufferbloatTest)
class BufferbloatTestAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('timestamp', 'baseline_rtt_ms', 'loaded_rtt_bidirectional_ms', 'classification')
    date_hierarchy = 'timestamp'


@admin.register(HourlyAggregate)
class HourlyAggregateAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('metric', 'target', 'period_start', 'avg_value', 'min_value', 'max_value', 'sample_count')
    list_filter = ('metric',)
    date_hierarchy = 'period_start'


@admin.register(DailyAggregate)
class DailyAggregateAdmin(ReadOnlyMeasurementAdmin):
    list_display = ('metric', 'target', 'period_start', 'avg_value', 'min_value', 'max_value', 'sample_count')
    list_filter = ('metric',)
    date_hierarchy = 'period_start'


    def has_change_permission(self, request, obj=None):
        return False
