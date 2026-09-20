from django.test import TestCase

from .models import (
    AddressFamily,
    MeasurementCategory,
    Protocol,
    RetentionPolicy,
    ScheduleConfig,
    Target,
    TargetCategory,
)


class TargetModelTests(TestCase):
    def test_create_target(self):
        target = Target.objects.create(
            name='Default Gateway',
            category=TargetCategory.GATEWAY,
            address='192.168.1.1',
            address_family=AddressFamily.IPV4,
            protocol=Protocol.ICMP,
        )
        self.assertTrue(target.enabled)
        self.assertIn('192.168.1.1', str(target))

    def test_name_must_be_unique(self):
        Target.objects.create(
            name='Cloudflare DNS', category=TargetCategory.DNS, address='1.1.1.1', protocol=Protocol.DNS
        )
        with self.assertRaises(Exception):
            Target.objects.create(
                name='Cloudflare DNS', category=TargetCategory.DNS, address='1.0.0.1', protocol=Protocol.DNS
            )


class ScheduleConfigSeedTests(TestCase):
    def test_defaults_seeded_by_migration(self):
        self.assertEqual(
            ScheduleConfig.objects.filter(task_type=MeasurementCategory.ICMP).count(), 1
        )
        icmp = ScheduleConfig.objects.get(task_type=MeasurementCategory.ICMP)
        self.assertTrue(icmp.enabled)
        self.assertEqual(icmp.interval_seconds, 30)

    def test_bandwidth_intensive_tests_default_disabled(self):
        throughput = ScheduleConfig.objects.get(task_type=MeasurementCategory.THROUGHPUT)
        bufferbloat = ScheduleConfig.objects.get(task_type=MeasurementCategory.BUFFERBLOAT)
        self.assertFalse(throughput.enabled)
        self.assertFalse(bufferbloat.enabled)


class RetentionPolicySeedTests(TestCase):
    def test_defaults_are_indefinite(self):
        policy = RetentionPolicy.objects.get(data_type=MeasurementCategory.ICMP)
        self.assertIsNone(policy.raw_retention_days)
        self.assertIsNone(policy.aggregate_retention_days)


class ElevationTests(TestCase):
    def test_is_elevated_returns_a_bool_on_windows(self):
        import sys

        from .elevation import is_elevated

        result = is_elevated()
        if sys.platform == 'win32':
            self.assertIn(result, (True, False))
        else:
            self.assertIsNone(result)

    def test_is_elevated_none_on_non_windows(self):
        from unittest.mock import patch

        from .elevation import is_elevated

        with patch('apps.core.elevation.sys.platform', 'linux'):
            self.assertIsNone(is_elevated())
