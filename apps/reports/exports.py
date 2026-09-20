"""Bulk export (§2/§32) — a raw data dump for an arbitrary date range, distinct from the curated
per-incident Report documents in generators.py (see docs/DECISIONS.md).
"""
import csv
import json

from django.http import HttpResponse

from apps.incidents.models import Incident
from apps.measurements.models import (
    BufferbloatTest,
    DNSMeasurement,
    HTTPMeasurement,
    ICMPMeasurement,
    InterfaceMetric,
    MTUTestResult,
    TCPMeasurement,
    ThroughputMeasurement,
)

EXPORTABLE_MEASUREMENTS = {
    'icmp': (ICMPMeasurement, ['timestamp', 'target', 'address_family', 'sent', 'received', 'loss_pct', 'avg_rtt_ms', 'jitter_ms', 'error']),
    'dns': (DNSMeasurement, ['timestamp', 'target', 'query_name', 'result_type', 'resolution_time_ms', 'resolved_ip']),
    'http': (HTTPMeasurement, ['timestamp', 'target', 'status_code', 'total_time_ms', 'error_type']),
    'tcp': (TCPMeasurement, ['timestamp', 'target', 'port', 'success', 'connect_time_ms', 'error_type']),
    'mtu': (MTUTestResult, ['timestamp', 'target', 'largest_successful_size', 'failure_threshold', 'df_behavior']),
    'throughput': (ThroughputMeasurement, ['timestamp', 'test_type', 'mbps_down', 'mbps_up', 'endpoint', 'error']),
    'bufferbloat': (BufferbloatTest, ['timestamp', 'baseline_rtt_ms', 'loaded_rtt_bidirectional_ms', 'classification']),
    'interface': (InterfaceMetric, ['timestamp', 'interface_name', 'state', 'bytes_sent', 'bytes_received']),
}


def _field_value(obj, field_name):
    value = getattr(obj, field_name, '')
    if field_name == 'target':
        return value.name if value is not None else ''
    return value


def export_measurements(data_type, window_start, window_end, fmt='csv'):
    """Returns an HttpResponse for the requested measurement type/format, or None if unknown."""
    entry = EXPORTABLE_MEASUREMENTS.get(data_type)
    if entry is None:
        return None
    model, fields = entry
    queryset = model.objects.filter(timestamp__gte=window_start, timestamp__lte=window_end).order_by('timestamp')

    if fmt == 'json':
        payload = [
            {field: _serialize(_field_value(obj, field)) for field in fields}
            for obj in queryset
        ]
        return HttpResponse(json.dumps(payload, indent=2), content_type='application/json')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{data_type}_export.csv"'
    writer = csv.writer(response)
    writer.writerow(fields)
    for obj in queryset:
        writer.writerow([_field_value(obj, field) for field in fields])
    return response


def export_incidents(window_start, window_end, fmt='csv'):
    fields = ['id', 'type', 'start_time', 'end_time', 'duration_seconds', 'severity', 'recovery_status', 'affected_destinations']
    queryset = Incident.objects.filter(start_time__gte=window_start, start_time__lte=window_end).order_by('start_time')

    if fmt == 'json':
        payload = [
            {
                'id': incident.id, 'type': incident.type, 'start_time': incident.start_time.isoformat(),
                'end_time': incident.end_time.isoformat() if incident.end_time else None,
                'duration_seconds': incident.duration_seconds, 'severity': incident.severity,
                'recovery_status': incident.recovery_status, 'affected_destinations': incident.affected_destinations,
            }
            for incident in queryset
        ]
        return HttpResponse(json.dumps(payload, indent=2), content_type='application/json')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="incidents_export.csv"'
    writer = csv.writer(response)
    writer.writerow(fields)
    for incident in queryset:
        writer.writerow([
            incident.id, incident.type, incident.start_time, incident.end_time, incident.duration_seconds,
            incident.severity, incident.recovery_status, ','.join(incident.affected_destinations or []),
        ])
    return response


def _serialize(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value
