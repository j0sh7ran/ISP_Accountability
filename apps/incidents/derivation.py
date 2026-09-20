"""Derives Events/Incidents from raw signals (state transitions, route changes, bufferbloat tests).

Uses qualifying language in descriptions ("Observed", "Consistent with") rather than asserting a
definitive root cause — see docs/STATE_MACHINE_AND_INCIDENTS.md and Requirements.md §21.
"""
from apps.measurements.models import BufferbloatTest, RouteChangeEvent
from apps.network_state.models import ConnectivityState, StateMachineConfig
from apps.reports.generators import generate_reports_for_incident
from apps.sla.engine import evaluate_rules_for_incident

from .models import Event, EventEvidence, EventType, Incident, RecoveryStatus, Severity


def handle_state_transition(state_log):
    """Called right after a NetworkStateLog row is created for a state that actually changed."""
    if state_log.new_state == ConnectivityState.OFFLINE:
        _open_outage_incident(state_log)
    elif state_log.new_state == ConnectivityState.ONLINE and state_log.previous_state == ConnectivityState.RECOVERING:
        _close_outage_incident(state_log)
    # DEGRADED transitions are recorded in NetworkStateLog but don't yet open a dedicated
    # incident/event — see docs/DECISIONS.md for the reasoning and this as a future extension point.


def _open_outage_incident(state_log):
    incident = Incident.objects.create(
        type=EventType.OUTAGE,
        start_time=state_log.timestamp,
        severity=Severity.CRITICAL,
        affected_tests=['icmp'],
        affected_destinations=state_log.confirming_targets,
        recovery_status=RecoveryStatus.ONGOING,
    )
    Event.objects.create(
        incident=incident,
        type=EventType.OUTAGE,
        start_time=state_log.timestamp,
        severity=Severity.CRITICAL,
        description=f'Observed connectivity loss: {state_log.reason}.',
    )


def _close_outage_incident(state_log):
    incident = (
        Incident.objects.filter(type__in=[EventType.OUTAGE, EventType.MICRO_OUTAGE], recovery_status=RecoveryStatus.ONGOING)
        .order_by('-start_time').first()
    )
    if incident is None:
        return  # nothing open to close — e.g. state log history predates this incident logic

    incident.end_time = state_log.timestamp
    incident.duration_seconds = int((incident.end_time - incident.start_time).total_seconds())
    incident.recovery_status = RecoveryStatus.RECOVERED

    config = StateMachineConfig.get_solo()
    if incident.duration_seconds < config.micro_outage_threshold_seconds:
        incident.type = EventType.MICRO_OUTAGE
    incident.save(update_fields=['end_time', 'duration_seconds', 'recovery_status', 'type'])

    event = incident.events.filter(end_time__isnull=True).order_by('-start_time').first()
    if event:
        event.end_time = state_log.timestamp
        event.type = incident.type
        event.description += f' Recovery observed: {state_log.reason}.'
        event.save(update_fields=['end_time', 'type', 'description'])

    evaluate_rules_for_incident(incident)
    generate_reports_for_incident(incident)



def derive_route_change_events():
    """Wrap any not-yet-processed RouteChangeEvent rows as standalone informational Events."""
    already_processed_ids = set(
        EventEvidence.objects.filter(measurement_type='RouteChangeEvent').values_list('measurement_id', flat=True)
    )
    new_changes = RouteChangeEvent.objects.exclude(id__in=already_processed_ids).order_by('timestamp')
    for change in new_changes:
        event = Event.objects.create(
            type=EventType.ROUTE_CHANGE,
            start_time=change.timestamp,
            end_time=change.timestamp,
            severity=Severity.WARNING if change.first_hop_changed else Severity.INFO,
            description=(
                f'Observed route change to {change.target.name}: hop count '
                f'{change.hop_count_before} -> {change.hop_count_after}'
                + (' (first hop changed)' if change.first_hop_changed else '') + '.'
            ),
        )
        EventEvidence.objects.create(event=event, measurement_type='RouteChangeEvent', measurement_id=change.id)


def derive_bufferbloat_events():
    """Wrap any not-yet-processed BufferbloatTest rows with a non-trivial classification as Events."""
    already_processed_ids = set(
        EventEvidence.objects.filter(measurement_type='BufferbloatTest').values_list('measurement_id', flat=True)
    )
    tests = (
        BufferbloatTest.objects.exclude(id__in=already_processed_ids)
        .exclude(classification__in=['', 'none', 'unclassified'])
        .order_by('timestamp')
    )
    for test in tests:
        event = Event.objects.create(
            type=EventType.BUFFERBLOAT,
            start_time=test.timestamp,
            end_time=test.timestamp,
            severity=Severity.CRITICAL if test.classification == 'severe' else Severity.WARNING,
            description=(
                f'Consistent with bufferbloat: latency increased under load '
                f'(baseline {test.baseline_rtt_ms:.0f}ms, loaded {test.loaded_rtt_bidirectional_ms or 0:.0f}ms), '
                f'classification "{test.classification}".'
            ),
        )
        EventEvidence.objects.create(event=event, measurement_type='BufferbloatTest', measurement_id=test.id)
