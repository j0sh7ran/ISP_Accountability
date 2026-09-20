"""Raw → hourly → daily aggregation (§31). Aggregates are preserved independently of raw-data
retention (see retention.py) so long-term trends survive even after raw rows are pruned.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Max, Min
from django.utils import timezone

from .models import DailyAggregate, DNSMeasurement, HourlyAggregate, ICMPMeasurement

# Same metric keys used by the dashboard/SLA engine, for consistency across the app.
METRIC_SOURCES = {
    'latency_ms': (ICMPMeasurement, 'avg_rtt_ms'),
    'packet_loss_pct': (ICMPMeasurement, 'loss_pct'),
    'jitter_ms': (ICMPMeasurement, 'jitter_ms'),
    'dns_resolution_ms': (DNSMeasurement, 'resolution_time_ms'),
}


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def aggregate_hour(metric, hour_start):
    """Roll up raw measurements for `metric` within [hour_start, hour_start + 1h) into one
    HourlyAggregate row per target. Idempotent — safe to re-run for the same hour.
    """
    model, field = METRIC_SOURCES[metric]
    hour_end = hour_start + timedelta(hours=1)
    base_qs = model.objects.filter(
        timestamp__gte=hour_start, timestamp__lt=hour_end, **{f'{field}__isnull': False}
    )

    # .order_by() clears the model's default ordering first — otherwise it leaks into the SELECT
    # and silently breaks DISTINCT (a classic Django/SQL gotcha).
    target_ids = base_qs.order_by().values_list('target_id', flat=True).distinct()
    created = []
    for target_id in target_ids:
        target_qs = base_qs.filter(target_id=target_id)
        stats = target_qs.aggregate(avg=Avg(field), min=Min(field), max=Max(field), count=Count('id'))
        values = sorted(target_qs.values_list(field, flat=True))
        aggregate, _ = HourlyAggregate.objects.update_or_create(
            target_id=target_id, metric=metric, period_start=hour_start,
            defaults={
                'avg_value': stats['avg'], 'min_value': stats['min'], 'max_value': stats['max'],
                'p95_value': _percentile(values, 95), 'sample_count': stats['count'],
            },
        )
        created.append(aggregate)
    return created


def aggregate_day(metric, day_start):
    """Roll up HourlyAggregate rows for `metric` on `day_start` into one DailyAggregate row per
    target. The daily p95 is an average of the day's hourly p95s — an approximation, not a true
    recomputation from raw data (see docs/DECISIONS.md).
    """
    day_end = day_start + timedelta(days=1)
    hourly_qs = HourlyAggregate.objects.filter(
        metric=metric, period_start__gte=day_start, period_start__lt=day_end,
    )
    # .order_by() clears the model's default ordering first — see the aggregate_hour() comment.
    target_ids = hourly_qs.order_by().values_list('target_id', flat=True).distinct()

    created = []
    for target_id in target_ids:
        rows = list(hourly_qs.filter(target_id=target_id))
        total_samples = sum(r.sample_count for r in rows)
        if total_samples == 0:
            continue
        weighted_avg = sum(r.avg_value * r.sample_count for r in rows) / total_samples
        aggregate, _ = DailyAggregate.objects.update_or_create(
            target_id=target_id, metric=metric, period_start=day_start.date(),
            defaults={
                'avg_value': weighted_avg,
                'min_value': min(r.min_value for r in rows),
                'max_value': max(r.max_value for r in rows),
                'p95_value': sum(r.p95_value for r in rows) / len(rows),
                'sample_count': total_samples,
            },
        )
        created.append(aggregate)
    return created


def run_aggregation(now=None):
    """Aggregates the most recently *completed* hour, and the most recently completed day once its
    last hour has rolled up. Safe to call repeatedly (e.g. every hour from the worker).
    """
    now = now or timezone.now()
    completed_hour_start = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    for metric in METRIC_SOURCES:
        aggregate_hour(metric, completed_hour_start)

    if completed_hour_start.hour == 23:
        day_start = completed_hour_start.replace(hour=0)
        for metric in METRIC_SOURCES:
            aggregate_day(metric, day_start)
