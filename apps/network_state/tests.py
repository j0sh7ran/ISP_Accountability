from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Protocol, Target, TargetCategory
from apps.incidents.models import Incident
from apps.measurements.models import ICMPMeasurement

from .evaluator import evaluate_and_log_state, evaluate_network_state
from .models import ConnectivityState, NetworkStateLog, StateMachineConfig


def _make_icmp(target, when, success=True):
    ICMPMeasurement.objects.create(
        target=target, timestamp=when, address_family=target.address_family,
        sent=4, received=4 if success else 0, loss_pct=0.0 if success else 100.0,
        error='' if success else 'timed out',
    )


class EvaluateNetworkStateTests(TestCase):
    def setUp(self):
        config = StateMachineConfig.get_solo()
        config.consecutive_failures_for_degraded = 2
        config.consecutive_failures_for_offline = 4
        config.min_independent_targets_failing = 2
        config.recovery_confirmation_successes = 3
        config.save()

        self.gateway = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        self.internet = Target.objects.create(
            name='Internet', category=TargetCategory.INTERNET, address='1.1.1.1', protocol=Protocol.ICMP,
        )

    def test_stays_online_with_only_one_target_failing(self):
        now = timezone.now()
        for i in range(5):
            _make_icmp(self.gateway, now + timedelta(seconds=i * 30), success=False)
        for i in range(5):
            _make_icmp(self.internet, now + timedelta(seconds=i * 30), success=True)

        new_state, reason, confirming = evaluate_network_state()

        self.assertEqual(new_state, ConnectivityState.ONLINE)

    def test_two_independent_targets_severely_failing_goes_offline(self):
        now = timezone.now()
        for target in (self.gateway, self.internet):
            for i in range(5):
                _make_icmp(target, now + timedelta(seconds=i * 30), success=False)

        new_state, reason, confirming = evaluate_network_state()

        self.assertEqual(new_state, ConnectivityState.OFFLINE)
        self.assertEqual(set(confirming), {'Gateway', 'Internet'})

    def test_recovery_passes_through_recovering_before_online(self):
        now = timezone.now()
        for target in (self.gateway, self.internet):
            for i in range(5):
                _make_icmp(target, now + timedelta(seconds=i * 30), success=False)
        log1 = evaluate_and_log_state(now=now + timedelta(minutes=3))
        self.assertEqual(log1.new_state, ConnectivityState.OFFLINE)

        # One success each — should move to RECOVERING, not straight to ONLINE.
        for target in (self.gateway, self.internet):
            _make_icmp(target, now + timedelta(minutes=4), success=True)
        log2 = evaluate_and_log_state(now=now + timedelta(minutes=4))
        self.assertEqual(log2.new_state, ConnectivityState.RECOVERING)

        # Sustained success (3 in a row) — should move to ONLINE.
        for target in (self.gateway, self.internet):
            for i in range(1, 3):
                _make_icmp(target, now + timedelta(minutes=4, seconds=i * 30), success=True)
        log3 = evaluate_and_log_state(now=now + timedelta(minutes=5))
        self.assertEqual(log3.new_state, ConnectivityState.ONLINE)


class EvaluateAndLogStateTests(TestCase):
    def test_no_log_created_when_state_unchanged(self):
        Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )

        result = evaluate_and_log_state()

        self.assertIsNone(result)
        self.assertEqual(NetworkStateLog.objects.count(), 0)

    def test_offline_transition_opens_an_incident(self):
        gateway = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        internet = Target.objects.create(
            name='Internet', category=TargetCategory.INTERNET, address='1.1.1.1', protocol=Protocol.ICMP,
        )
        now = timezone.now()
        for target in (gateway, internet):
            for i in range(5):
                _make_icmp(target, now + timedelta(seconds=i * 30), success=False)

        evaluate_and_log_state(now=now)

        self.assertEqual(Incident.objects.filter(recovery_status='ongoing').count(), 1)
