from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Protocol, Target, TargetCategory
from apps.incidents.models import EventType, Incident, RecoveryStatus, Severity
from apps.measurements.models import DNSMeasurement, ICMPMeasurement

from .engine import evaluate_periodic_rules, evaluate_rule, evaluate_rules_for_incident
from .models import SLAEvaluationStatus, SLAMetric, SLAOperator, SLARule


class EvaluateRuleTests(TestCase):
    def setUp(self):
        self.target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )

    def test_insufficient_data_when_no_measurements_exist(self):
        rule = SLARule.objects.create(
            name='Packet loss', metric=SLAMetric.PACKET_LOSS_PCT, operator=SLAOperator.GT, threshold=2.0,
            measurement_window_seconds=3600,
        )
        now = timezone.now()

        evaluation = evaluate_rule(rule, now - timedelta(hours=1), now)

        self.assertEqual(evaluation.status, SLAEvaluationStatus.INSUFFICIENT_DATA)
        self.assertIsNone(evaluation.observed_value)

    def test_breached_when_average_loss_exceeds_threshold(self):
        rule = SLARule.objects.create(
            name='Packet loss', metric=SLAMetric.PACKET_LOSS_PCT, operator=SLAOperator.GT, threshold=2.0,
            measurement_window_seconds=3600,
        )
        now = timezone.now()
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=now - timedelta(minutes=1), address_family='ipv4',
            sent=4, received=1, loss_pct=75.0,
        )

        evaluation = evaluate_rule(rule, now - timedelta(hours=1), now)

        self.assertEqual(evaluation.status, SLAEvaluationStatus.BREACHED)
        self.assertEqual(evaluation.observed_value, 75.0)

    def test_satisfied_when_within_threshold(self):
        rule = SLARule.objects.create(
            name='Packet loss', metric=SLAMetric.PACKET_LOSS_PCT, operator=SLAOperator.GT, threshold=2.0,
            measurement_window_seconds=3600,
        )
        now = timezone.now()
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=now - timedelta(minutes=1), address_family='ipv4',
            sent=4, received=4, loss_pct=0.0,
        )

        evaluation = evaluate_rule(rule, now - timedelta(hours=1), now)

        self.assertEqual(evaluation.status, SLAEvaluationStatus.SATISFIED)

    def test_min_duration_below_threshold_is_treated_as_satisfied(self):
        rule = SLARule.objects.create(
            name='Outage rule', metric=SLAMetric.PACKET_LOSS_PCT, operator=SLAOperator.GT, threshold=2.0,
            measurement_window_seconds=3600, min_duration_seconds=300,
        )
        now = timezone.now()
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=now - timedelta(minutes=1), address_family='ipv4',
            sent=4, received=0, loss_pct=100.0,
        )
        incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timedelta(seconds=30), end_time=now,
            duration_seconds=30, severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
        )

        evaluation = evaluate_rule(rule, now - timedelta(hours=1), now, incident=incident)

        self.assertEqual(evaluation.status, SLAEvaluationStatus.SATISFIED)
        self.assertIn('min_duration_seconds', evaluation.evidence['note'])

    def test_dns_resolution_metric(self):
        Target.objects.create(name='Cloudflare DNS', category=TargetCategory.DNS, address='1.1.1.1', protocol=Protocol.DNS)
        rule = SLARule.objects.create(
            name='DNS latency', metric=SLAMetric.DNS_RESOLUTION_MS, operator=SLAOperator.GT, threshold=100.0,
            measurement_window_seconds=3600,
        )
        now = timezone.now()
        DNSMeasurement.objects.create(
            target=Target.objects.get(name='Cloudflare DNS'), timestamp=now - timedelta(minutes=1),
            resolver='1.1.1.1', query_name='example.com', query_type='A', address_family='ipv4',
            resolution_time_ms=8.0, result_type='success',
        )

        evaluation = evaluate_rule(rule, now - timedelta(hours=1), now)

        self.assertEqual(evaluation.status, SLAEvaluationStatus.SATISFIED)
        self.assertEqual(evaluation.observed_value, 8.0)


class AvailabilityMetricTests(TestCase):
    def test_availability_reflects_outage_overlap(self):
        now = timezone.now()
        window_start = now - timedelta(hours=1)
        Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timedelta(minutes=30), end_time=now - timedelta(minutes=24),
            duration_seconds=360, severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
        )
        rule = SLARule.objects.create(
            name='Availability', metric=SLAMetric.AVAILABILITY_PCT, operator=SLAOperator.LT, threshold=99.9,
            measurement_window_seconds=3600,
        )

        evaluation = evaluate_rule(rule, window_start, now)

        # 360s outage in a 3600s window -> ~90% availability, well below any reasonable threshold.
        self.assertEqual(evaluation.status, SLAEvaluationStatus.BREACHED)
        self.assertAlmostEqual(evaluation.observed_value, 90.0, delta=0.1)

    def test_no_outage_means_full_availability(self):
        now = timezone.now()
        rule = SLARule.objects.create(
            name='Availability', metric=SLAMetric.AVAILABILITY_PCT, operator=SLAOperator.LT, threshold=99.9,
            measurement_window_seconds=3600,
        )

        evaluation = evaluate_rule(rule, now - timedelta(hours=1), now)

        self.assertEqual(evaluation.observed_value, 100.0)
        self.assertEqual(evaluation.status, SLAEvaluationStatus.SATISFIED)


class EvaluateRulesForIncidentTests(TestCase):
    def test_only_matching_destination_filter_rules_are_evaluated(self):
        SLARule.objects.create(
            name='Gateway loss', metric=SLAMetric.PACKET_LOSS_PCT, operator=SLAOperator.GT, threshold=2.0,
            measurement_window_seconds=3600, destination_filter='Gateway',
        )
        SLARule.objects.create(
            name='DNS loss', metric=SLAMetric.PACKET_LOSS_PCT, operator=SLAOperator.GT, threshold=2.0,
            measurement_window_seconds=3600, destination_filter='Cloudflare',
        )
        now = timezone.now()
        incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timedelta(minutes=5), end_time=now, duration_seconds=300,
            severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED, affected_destinations=['Gateway'],
        )

        evaluations = evaluate_rules_for_incident(incident)

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0].rule.name, 'Gateway loss')

    def test_returns_nothing_for_an_open_incident(self):
        incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=timezone.now(), severity=Severity.CRITICAL,
            recovery_status=RecoveryStatus.ONGOING,
        )

        self.assertEqual(evaluate_rules_for_incident(incident), [])


class EvaluatePeriodicRulesTests(TestCase):
    def test_evaluates_every_enabled_rule_with_a_window(self):
        SLARule.objects.create(
            name='Monthly availability', metric=SLAMetric.AVAILABILITY_PCT, operator=SLAOperator.LT,
            threshold=99.9, measurement_window_seconds=2592000,
        )
        SLARule.objects.create(
            name='Disabled rule', metric=SLAMetric.AVAILABILITY_PCT, operator=SLAOperator.LT,
            threshold=99.9, measurement_window_seconds=2592000, enabled=False,
        )

        results = evaluate_periodic_rules()

        self.assertEqual(len(results), 1)
