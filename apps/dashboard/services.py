"""Data-fetching helpers for the dashboard views/API (§24-25). Kept separate from views.py so the
query logic is unit-testable without going through HTTP.
"""
from datetime import timedelta

from django.db.models import Avg
from django.utils import timezone

from apps.core.models import (
    MeasurementCategory,
    OnDemandTestRequest,
    OnDemandTestStatus,
    ScheduleConfig,
    Target,
    TargetCategory,
)
from apps.baselines.comparison import compare_metric
from apps.incidents.models import EventType, Incident, RecoveryStatus
from apps.measurements.models import DNSMeasurement, DNSResultType, HTTPMeasurement, ICMPMeasurement, RouteChangeEvent
from apps.measurements.retention import RAW_MODELS_BY_DATA_TYPE
from apps.network_state.models import NetworkStateLog
from apps.sla.engine import compute_availability_pct
from apps.sla.models import SLAEvaluation, SLAEvaluationStatus, SLARule

# Recent-row "did this job error" checks, keyed by ScheduleConfig.task_type. Only defined for
# categories with an unambiguous per-row error signal — others just report a row count (see
# job_status_summary()).
JOB_ERROR_FILTERS = {
    'icmp': lambda qs: qs.exclude(error=''),
    'http': lambda qs: qs.exclude(error_type=''),
    'tcp': lambda qs: qs.exclude(error_type=''),
    'throughput': lambda qs: qs.exclude(error=''),
    'dns': lambda qs: qs.exclude(result_type=DNSResultType.SUCCESS),
}

RANGE_CHOICES = {
    '1h': timedelta(hours=1),
    '6h': timedelta(hours=6),
    '24h': timedelta(hours=24),
    '7d': timedelta(days=7),
    '30d': timedelta(days=30),
}


def resolve_range(range_key, custom_start=None, custom_end=None):
    """Turn a range key (or explicit custom start/end) into (start, end) datetimes."""
    now = timezone.now()
    if range_key == 'custom' and custom_start and custom_end:
        return custom_start, custom_end
    delta = RANGE_CHOICES.get(range_key, RANGE_CHOICES['24h'])
    return now - delta, now


def current_state():
    return NetworkStateLog.current_state()


def latest_icmp_by_target(address_family=None):
    """Most recent ICMPMeasurement per confirming target — the "current connectivity" snapshot."""
    targets = Target.objects.filter(
        enabled=True, category__in=[TargetCategory.GATEWAY, TargetCategory.ISP_HOP, TargetCategory.INTERNET]
    )
    if address_family:
        targets = targets.filter(address_family=address_family)

    rows = []
    for target in targets:
        latest = ICMPMeasurement.objects.filter(target=target).order_by('-timestamp').first()
        rows.append({'target': target, 'measurement': latest})
    return rows


def latest_dns_status():
    latest_per_resolver = []
    for target in Target.objects.filter(enabled=True, category=TargetCategory.DNS):
        latest = DNSMeasurement.objects.filter(target=target).order_by('-timestamp').first()
        latest_per_resolver.append({'target': target, 'measurement': latest})
    return latest_per_resolver


def latest_http_status():
    latest_per_endpoint = []
    for target in Target.objects.filter(enabled=True, category=TargetCategory.HTTP):
        latest = HTTPMeasurement.objects.filter(target=target).order_by('-timestamp').first()
        latest_per_endpoint.append({'target': target, 'measurement': latest})
    return latest_per_endpoint


def active_incidents():
    return list(Incident.objects.filter(recovery_status=RecoveryStatus.ONGOING).order_by('-start_time'))


def recent_incidents(limit=10):
    return list(Incident.objects.order_by('-start_time')[:limit])


def recent_sla_violations(limit=10):
    return list(
        SLAEvaluation.objects.filter(status=SLAEvaluationStatus.BREACHED).order_by('-window_end')[:limit]
    )


def uptime_pct(hours=24):
    window_end = timezone.now()
    window_start = window_end - timedelta(hours=hours)
    return compute_availability_pct(window_start, window_end)


def job_status_summary():
    """Near-real-time health snapshot of every scheduled worker job (§17/§24), read entirely from
    ScheduleConfig + recent measurement rows — the web process and worker process only share a DB
    (see docs/WORKER_AND_SCHEDULING.md), there's no in-memory link between them.
    """
    now = timezone.now()
    pending_on_demand = OnDemandTestRequest.objects.filter(
        task_type__in=[MeasurementCategory.THROUGHPUT, MeasurementCategory.BUFFERBLOAT],
        status__in=[OnDemandTestStatus.PENDING, OnDemandTestStatus.RUNNING],
    ).count()

    rows = []
    for schedule in ScheduleConfig.objects.all():
        model = RAW_MODELS_BY_DATA_TYPE.get(schedule.task_type)
        recent_count = error_count = None
        if model is not None:
            lookback = now - timedelta(seconds=max(schedule.interval_seconds * 3, 300))
            recent_qs = model.objects.filter(timestamp__gte=lookback)
            recent_count = recent_qs.count()
            error_filter = JOB_ERROR_FILTERS.get(schedule.task_type)
            if error_filter is not None:
                error_count = error_filter(recent_qs).count()

        seconds_since_last_run = (now - schedule.last_run).total_seconds() if schedule.last_run else None

        if not schedule.enabled:
            status = 'disabled'
        elif schedule.last_run is None:
            status = 'pending'
        elif seconds_since_last_run > schedule.interval_seconds * 2 + 30:
            status = 'overdue'
        elif error_count and recent_count and error_count == recent_count:
            status = 'error'
        else:
            status = 'ok'

        rows.append({
            'task_type': schedule.task_type,
            'label': schedule.get_task_type_display(),
            'enabled': schedule.enabled,
            'interval_seconds': schedule.interval_seconds,
            'last_run': schedule.last_run,
            'seconds_since_last_run': seconds_since_last_run,
            'recent_count': recent_count,
            'error_count': error_count,
            'status': status,
        })

    return {'jobs': rows, 'pending_on_demand': pending_on_demand}


def ipv4_ipv6_summary():
    """Latest connectivity + loss/latency snapshot split by address family, for the IPv4/IPv6 view."""
    summary = {}
    for family in ('ipv4', 'ipv6'):
        qs = ICMPMeasurement.objects.filter(address_family=family).order_by('-timestamp')
        latest = qs.first()
        recent_avg = qs[:20].aggregate(avg_loss=Avg('loss_pct'), avg_rtt=Avg('avg_rtt_ms'))
        summary[family] = {
            'latest': latest,
            'avg_loss_pct': recent_avg['avg_loss'],
            'avg_rtt_ms': recent_avg['avg_rtt'],
        }
    return summary


METRIC_FIELD_MAP = {
    'latency_ms': (ICMPMeasurement, 'avg_rtt_ms'),
    'packet_loss_pct': (ICMPMeasurement, 'loss_pct'),
    'jitter_ms': (ICMPMeasurement, 'jitter_ms'),
    'dns_resolution_ms': (DNSMeasurement, 'resolution_time_ms'),
}


def timeseries(metric, window_start, window_end, address_family=None):
    """Raw (timestamp, value) points for a metric within a window — feeds the Chart.js graphs page."""
    mapping = METRIC_FIELD_MAP.get(metric)
    if mapping is None:
        return []
    model, field = mapping
    qs = model.objects.filter(timestamp__gte=window_start, timestamp__lte=window_end).exclude(**{f'{field}__isnull': True})
    if address_family and hasattr(model, 'address_family'):
        qs = qs.filter(address_family=address_family)
    qs = qs.order_by('timestamp').values_list('timestamp', field)
    return [{'timestamp': ts.isoformat(), 'value': value} for ts, value in qs]


COMPARISON_METRICS = ['latency_ms', 'packet_loss_pct', 'jitter_ms', 'dns_resolution_ms']


def _avg(points):
    values = [p['value'] for p in points]
    return sum(values) / len(values) if values else None


def period_stats(window_start, window_end):
    """Underlying per-period figures for the historical comparison view (§28) — never collapsed
    into a single score.
    """
    stats = {'uptime_pct': compute_availability_pct(window_start, window_end)}
    for metric in COMPARISON_METRICS:
        stats[metric] = _avg(timeseries(metric, window_start, window_end))
    stats['outage_count'] = Incident.objects.filter(
        type__in=[EventType.OUTAGE, EventType.MICRO_OUTAGE], start_time__gte=window_start, start_time__lt=window_end,
    ).count()
    stats['route_change_count'] = RouteChangeEvent.objects.filter(
        timestamp__gte=window_start, timestamp__lt=window_end,
    ).count()
    return stats


def historical_comparison(hours=24):
    """Current period vs. the immediately preceding period of the same length (§28)."""
    now = timezone.now()
    current_start, current_end = now - timedelta(hours=hours), now
    previous_start, previous_end = current_start - timedelta(hours=hours), current_start
    return {
        'current': period_stats(current_start, current_end),
        'previous': period_stats(previous_start, previous_end),
        'hours': hours,
    }


def sla_comparison_rows():
    """Latest evaluation per enabled SLARule (§30) — kept separate from baseline comparisons."""
    latest_by_rule = {}
    for evaluation in SLAEvaluation.objects.order_by('rule_id', '-window_end'):
        latest_by_rule.setdefault(evaluation.rule_id, evaluation)
    return [
        {'rule': rule, 'evaluation': latest_by_rule.get(rule.id)}
        for rule in SLARule.objects.filter(enabled=True)
    ]


def baseline_comparison_rows(hours=24):
    """Observed vs. industry Baseline (§29) — descriptive only, never pass/fail."""
    now = timezone.now()
    window_start = now - timedelta(hours=hours)
    rows = []
    for metric in COMPARISON_METRICS:
        observed = _avg(timeseries(metric, window_start, now))
        comparison = compare_metric(metric, observed) if observed is not None else None
        rows.append({'metric': metric, 'observed': observed, 'comparison': comparison})
    return rows
