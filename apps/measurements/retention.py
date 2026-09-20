"""Retention enforcement (§31) — deletes raw/aggregate rows older than each RetentionPolicy's
configured age. Incidents and SLA evaluations are never touched here regardless of policy, since
they aren't measurement categories with a RetentionPolicy row.

Raw rows referenced by an EventEvidence entry may still be pruned once their retention window
passes — the Event's own description text is the durable record of what was observed; see
docs/DECISIONS.md.
"""
from datetime import timedelta

from django.utils import timezone

from apps.core.models import RetentionPolicy
from apps.measurements.models import (
    BufferbloatTest,
    DailyAggregate,
    DNSMeasurement,
    HourlyAggregate,
    HTTPMeasurement,
    ICMPMeasurement,
    InterfaceMetric,
    MTUTestResult,
    RouteTestRun,
    TCPMeasurement,
    ThroughputMeasurement,
)

RAW_MODELS_BY_DATA_TYPE = {
    'icmp': ICMPMeasurement,
    'dns': DNSMeasurement,
    'http': HTTPMeasurement,
    'tcp': TCPMeasurement,
    'route': RouteTestRun,  # RouteHop/RouteChangeEvent cascade or are independently timestamped
    'mtu': MTUTestResult,
    'throughput': ThroughputMeasurement,
    'bufferbloat': BufferbloatTest,
    'interface': InterfaceMetric,
}


def enforce_retention(now=None):
    """Deletes raw rows older than `raw_retention_days` and aggregate rows older than
    `aggregate_retention_days`, per RetentionPolicy. A blank/None value means "keep indefinitely".
    """
    now = now or timezone.now()
    deleted = {'raw': 0, 'hourly': 0, 'daily': 0}

    for policy in RetentionPolicy.objects.all():
        model = RAW_MODELS_BY_DATA_TYPE.get(policy.data_type)
        if model and policy.raw_retention_days:
            cutoff = now - timedelta(days=policy.raw_retention_days)
            count, _ = model.objects.filter(timestamp__lt=cutoff).delete()
            deleted['raw'] += count

        if policy.aggregate_retention_days:
            cutoff = now - timedelta(days=policy.aggregate_retention_days)
            hourly_count, _ = HourlyAggregate.objects.filter(
                metric__in=_metrics_for_data_type(policy.data_type), period_start__lt=cutoff
            ).delete()
            daily_count, _ = DailyAggregate.objects.filter(
                metric__in=_metrics_for_data_type(policy.data_type), period_start__lt=cutoff.date()
            ).delete()
            deleted['hourly'] += hourly_count
            deleted['daily'] += daily_count

    return deleted


def _metrics_for_data_type(data_type):
    """Maps a RetentionPolicy.data_type back to the aggregate metric keys derived from it."""
    from apps.measurements.aggregation import METRIC_SOURCES

    return [
        metric for metric, (model, _field) in METRIC_SOURCES.items()
        if RAW_MODELS_BY_DATA_TYPE.get(data_type) is model
    ]
