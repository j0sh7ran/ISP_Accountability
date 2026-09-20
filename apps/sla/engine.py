"""SLA evaluation engine (§22). Computes an observed value for a rule's metric over a window, and
compares it against the rule's threshold — never silently assuming compliance when data is missing.
"""
from datetime import timedelta

from django.db.models import Avg, Max, Q
from django.utils import timezone

from apps.incidents.models import EventType, Incident
from apps.measurements.models import DNSMeasurement, ICMPMeasurement, ThroughputMeasurement

from .models import SLAEvaluation, SLAEvaluationStatus, SLAMetric, SLAOperator, SLARule


def _apply_destination_filter(queryset, destination_filter):
    if not destination_filter:
        return queryset
    return queryset.filter(
        Q(target__name__icontains=destination_filter) | Q(target__address__icontains=destination_filter)
    )


def _compute_packet_loss_pct(window_start, window_end, destination_filter, protocol):
    qs = _apply_destination_filter(
        ICMPMeasurement.objects.filter(timestamp__gte=window_start, timestamp__lte=window_end), destination_filter
    )
    if not qs.exists():
        return None, {'sample_count': 0}
    return qs.aggregate(avg=Avg('loss_pct'))['avg'], {'sample_count': qs.count()}


def _compute_latency_ms(window_start, window_end, destination_filter, protocol):
    qs = _apply_destination_filter(
        ICMPMeasurement.objects.filter(
            timestamp__gte=window_start, timestamp__lte=window_end, avg_rtt_ms__isnull=False
        ),
        destination_filter,
    )
    if not qs.exists():
        return None, {'sample_count': 0}
    return qs.aggregate(avg=Avg('avg_rtt_ms'))['avg'], {'sample_count': qs.count()}


def _compute_jitter_ms(window_start, window_end, destination_filter, protocol):
    qs = _apply_destination_filter(
        ICMPMeasurement.objects.filter(
            timestamp__gte=window_start, timestamp__lte=window_end, jitter_ms__isnull=False
        ),
        destination_filter,
    )
    if not qs.exists():
        return None, {'sample_count': 0}
    return qs.aggregate(avg=Avg('jitter_ms'))['avg'], {'sample_count': qs.count()}


def _compute_dns_resolution_ms(window_start, window_end, destination_filter, protocol):
    qs = _apply_destination_filter(
        DNSMeasurement.objects.filter(
            timestamp__gte=window_start, timestamp__lte=window_end, resolution_time_ms__isnull=False
        ),
        destination_filter,
    )
    if not qs.exists():
        return None, {'sample_count': 0}
    return qs.aggregate(avg=Avg('resolution_time_ms'))['avg'], {'sample_count': qs.count()}


def _compute_throughput_mbps(window_start, window_end, destination_filter, protocol):
    qs = ThroughputMeasurement.objects.filter(
        timestamp__gte=window_start, timestamp__lte=window_end, mbps_down__isnull=False
    )
    if not qs.exists():
        return None, {'sample_count': 0}
    return qs.aggregate(avg=Avg('mbps_down'))['avg'], {'sample_count': qs.count()}


def _outages_overlapping_window(window_start, window_end):
    return Incident.objects.filter(
        type__in=[EventType.OUTAGE, EventType.MICRO_OUTAGE], start_time__lt=window_end
    ).filter(Q(end_time__gt=window_start) | Q(end_time__isnull=True))


def _compute_availability_pct(window_start, window_end, destination_filter, protocol):
    window_seconds = (window_end - window_start).total_seconds()
    if window_seconds <= 0:
        return None, {}

    outage_seconds = 0.0
    incident_ids = []
    for incident in _outages_overlapping_window(window_start, window_end):
        overlap_start = max(incident.start_time, window_start)
        overlap_end = min(incident.end_time, window_end) if incident.end_time else window_end
        outage_seconds += max((overlap_end - overlap_start).total_seconds(), 0)
        incident_ids.append(incident.id)

    availability = max(0.0, 100.0 * (1 - outage_seconds / window_seconds))
    return availability, {'outage_seconds': outage_seconds, 'incident_ids': incident_ids}


def compute_availability_pct(window_start, window_end):
    """Public entry point for callers outside the engine (e.g. the dashboard) needing just this metric."""
    value, _evidence = _compute_availability_pct(window_start, window_end, '', '')
    return value


def _compute_outage_duration_s(window_start, window_end, destination_filter, protocol):
    incidents = Incident.objects.filter(
        type__in=[EventType.OUTAGE, EventType.MICRO_OUTAGE],
        start_time__gte=window_start, start_time__lte=window_end, duration_seconds__isnull=False,
    )
    if not incidents.exists():
        # No outages observed is itself a known, valid measurement — not "insufficient data".
        return 0.0, {'incident_ids': []}
    return (
        float(incidents.aggregate(m=Max('duration_seconds'))['m']),
        {'incident_ids': list(incidents.values_list('id', flat=True))},
    )


METRIC_COMPUTERS = {
    SLAMetric.PACKET_LOSS_PCT: _compute_packet_loss_pct,
    SLAMetric.LATENCY_MS: _compute_latency_ms,
    SLAMetric.JITTER_MS: _compute_jitter_ms,
    SLAMetric.AVAILABILITY_PCT: _compute_availability_pct,
    SLAMetric.OUTAGE_DURATION_S: _compute_outage_duration_s,
    SLAMetric.THROUGHPUT_MBPS: _compute_throughput_mbps,
    SLAMetric.DNS_RESOLUTION_MS: _compute_dns_resolution_ms,
}


def _compare(observed, operator, threshold):
    if operator == SLAOperator.GT:
        return observed > threshold
    if operator == SLAOperator.GTE:
        return observed >= threshold
    if operator == SLAOperator.LT:
        return observed < threshold
    if operator == SLAOperator.LTE:
        return observed <= threshold
    if operator == SLAOperator.EQ:
        return observed == threshold
    raise ValueError(f'Unknown SLA operator: {operator}')


def evaluate_rule(rule, window_start, window_end, incident=None):
    """Evaluate a single rule over [window_start, window_end] and persist the result."""
    computer = METRIC_COMPUTERS.get(rule.metric)
    if computer is None:
        return None

    observed_value, evidence = computer(window_start, window_end, rule.destination_filter, rule.protocol)
    evidence = {**evidence, 'window_start': window_start.isoformat(), 'window_end': window_end.isoformat()}

    if observed_value is None:
        status = SLAEvaluationStatus.INSUFFICIENT_DATA
    elif rule.min_duration_seconds and incident is not None and (incident.duration_seconds or 0) < rule.min_duration_seconds:
        # The underlying condition didn't hold long enough to count as a breach (§22 min_duration).
        status = SLAEvaluationStatus.SATISFIED
        evidence['note'] = (
            f'Incident duration {incident.duration_seconds}s is below the rule\'s '
            f'min_duration_seconds={rule.min_duration_seconds}s'
        )
    else:
        breached = _compare(observed_value, rule.operator, rule.threshold)
        status = SLAEvaluationStatus.BREACHED if breached else SLAEvaluationStatus.SATISFIED

    return SLAEvaluation.objects.create(
        rule=rule, incident=incident, window_start=window_start, window_end=window_end,
        observed_value=observed_value, threshold_value=rule.threshold, status=status, evidence=evidence,
    )


def _rule_applies_to_incident(rule, incident):
    if not rule.destination_filter:
        return True
    destinations = [str(d).lower() for d in (incident.affected_destinations or [])]
    return any(rule.destination_filter.lower() in d for d in destinations)


def evaluate_rules_for_incident(incident):
    """Triggered when an incident closes (§22) — evaluates every enabled rule whose destination
    filter matches the incident's evidence, over the incident's own start/end window.
    """
    if incident.end_time is None:
        return []
    rules = [r for r in SLARule.objects.filter(enabled=True) if _rule_applies_to_incident(r, incident)]
    return [evaluate_rule(rule, incident.start_time, incident.end_time, incident=incident) for rule in rules]


def evaluate_periodic_rules(now=None):
    """Triggered periodically (e.g. daily) for window-based rules like monthly availability (§22)."""
    now = now or timezone.now()
    results = []
    for rule in SLARule.objects.filter(enabled=True, measurement_window_seconds__gt=0):
        window_end = now
        window_start = now - timedelta(seconds=rule.measurement_window_seconds)
        results.append(evaluate_rule(rule, window_start, window_end))
    return results
