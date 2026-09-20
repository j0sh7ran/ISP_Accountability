from django.test import TestCase
from django.utils import timezone

from apps.core.models import Protocol, Target, TargetCategory
from apps.measurements.models import BufferbloatTest, RouteChangeEvent
from apps.network_state.models import ConnectivityState, NetworkStateLog, StateMachineConfig

from .derivation import derive_bufferbloat_events, derive_route_change_events, handle_state_transition
from .models import Event, EventEvidence, EventType, Incident, RecoveryStatus


class HandleStateTransitionTests(TestCase):
    def test_offline_transition_opens_an_ongoing_incident_and_event(self):
        log = NetworkStateLog.objects.create(
            timestamp=timezone.now(), previous_state=ConnectivityState.DEGRADED,
            new_state=ConnectivityState.OFFLINE, reason='2 independent targets failing',
            confirming_targets=['Gateway', 'Internet'],
        )

        handle_state_transition(log)

        incident = Incident.objects.get()
        self.assertEqual(incident.type, EventType.OUTAGE)
        self.assertEqual(incident.recovery_status, RecoveryStatus.ONGOING)
        event = incident.events.get()
        self.assertIn('Observed', event.description)

    def test_recovery_closes_incident_and_computes_duration(self):
        start = timezone.now()
        opened = NetworkStateLog.objects.create(
            timestamp=start, previous_state=ConnectivityState.DEGRADED, new_state=ConnectivityState.OFFLINE,
            reason='failing', confirming_targets=['Gateway'],
        )
        handle_state_transition(opened)

        closed = NetworkStateLog.objects.create(
            timestamp=start + timezone.timedelta(minutes=10), previous_state=ConnectivityState.RECOVERING,
            new_state=ConnectivityState.ONLINE, reason='recovered', confirming_targets=['Gateway'],
        )
        handle_state_transition(closed)

        incident = Incident.objects.get()
        self.assertEqual(incident.recovery_status, RecoveryStatus.RECOVERED)
        self.assertEqual(incident.duration_seconds, 600)
        self.assertEqual(incident.type, EventType.OUTAGE)  # 10 minutes exceeds the micro-outage threshold

    def test_short_outage_is_classified_as_micro_outage(self):
        StateMachineConfig.get_solo()  # ensure the default 60s threshold row exists
        start = timezone.now()
        opened = NetworkStateLog.objects.create(
            timestamp=start, previous_state=ConnectivityState.DEGRADED, new_state=ConnectivityState.OFFLINE,
            reason='failing', confirming_targets=['Gateway'],
        )
        handle_state_transition(opened)

        closed = NetworkStateLog.objects.create(
            timestamp=start + timezone.timedelta(seconds=20), previous_state=ConnectivityState.RECOVERING,
            new_state=ConnectivityState.ONLINE, reason='recovered', confirming_targets=['Gateway'],
        )
        handle_state_transition(closed)

        incident = Incident.objects.get()
        self.assertEqual(incident.type, EventType.MICRO_OUTAGE)

    def test_recovery_triggers_sla_evaluation(self):
        from apps.sla.models import SLAEvaluationStatus, SLAMetric, SLAOperator, SLARule

        SLARule.objects.create(
            name='Availability', metric=SLAMetric.AVAILABILITY_PCT, operator=SLAOperator.LT,
            threshold=99.9, measurement_window_seconds=3600,
        )
        start = timezone.now()
        opened = NetworkStateLog.objects.create(
            timestamp=start, previous_state=ConnectivityState.DEGRADED, new_state=ConnectivityState.OFFLINE,
            reason='failing', confirming_targets=['Gateway'],
        )
        handle_state_transition(opened)
        closed = NetworkStateLog.objects.create(
            timestamp=start + timezone.timedelta(minutes=10), previous_state=ConnectivityState.RECOVERING,
            new_state=ConnectivityState.ONLINE, reason='recovered', confirming_targets=['Gateway'],
        )

        handle_state_transition(closed)

        incident = Incident.objects.get()
        evaluation = incident.sla_evaluations.get()
        self.assertEqual(evaluation.status, SLAEvaluationStatus.BREACHED)

    def test_recovery_triggers_report_generation(self):
        start = timezone.now()
        opened = NetworkStateLog.objects.create(
            timestamp=start, previous_state=ConnectivityState.DEGRADED, new_state=ConnectivityState.OFFLINE,
            reason='failing', confirming_targets=['Gateway'],
        )
        handle_state_transition(opened)
        closed = NetworkStateLog.objects.create(
            timestamp=start + timezone.timedelta(minutes=10), previous_state=ConnectivityState.RECOVERING,
            new_state=ConnectivityState.ONLINE, reason='recovered', confirming_targets=['Gateway'],
        )

        handle_state_transition(closed)

        incident = Incident.objects.get()
        self.assertEqual(incident.reports.count(), 4)


class DeriveRouteChangeEventsTests(TestCase):
    def test_creates_an_event_per_unprocessed_change(self):
        target = Target.objects.create(
            name='Internet', category=TargetCategory.INTERNET, address='1.1.1.1', protocol=Protocol.ICMP,
        )
        RouteChangeEvent.objects.create(
            target=target, timestamp=timezone.now(), previous_route_hash='a', new_route_hash='b',
            hop_count_before=5, hop_count_after=6, first_hop_changed=True,
        )

        derive_route_change_events()
        derive_route_change_events()  # idempotent — should not create a duplicate

        self.assertEqual(Event.objects.filter(type=EventType.ROUTE_CHANGE).count(), 1)
        self.assertEqual(EventEvidence.objects.filter(measurement_type='RouteChangeEvent').count(), 1)


class DeriveBufferbloatEventsTests(TestCase):
    def test_ignores_none_classification(self):
        BufferbloatTest.objects.create(timestamp=timezone.now(), baseline_rtt_ms=10.0, classification='none')

        derive_bufferbloat_events()

        self.assertEqual(Event.objects.count(), 0)

    def test_creates_event_for_severe_classification(self):
        BufferbloatTest.objects.create(
            timestamp=timezone.now(), baseline_rtt_ms=10.0, loaded_rtt_bidirectional_ms=150.0,
            classification='severe',
        )

        derive_bufferbloat_events()

        event = Event.objects.get()
        self.assertEqual(event.type, EventType.BUFFERBLOAT)
        self.assertIn('Consistent with', event.description)
