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
    def test_is_elevated_returns_a_bool_or_none_for_the_real_platform(self):
        import sys

        from .elevation import is_elevated

        result = is_elevated()
        if sys.platform in ('win32', 'linux', 'darwin'):
            self.assertIn(result, (True, False))
        else:
            self.assertIsNone(result)

    def test_windows_admin_true(self):
        from unittest.mock import patch

        from .elevation import is_elevated

        with patch('apps.core.elevation.sys.platform', 'win32'), \
                patch('apps.core.elevation.ctypes.windll.shell32.IsUserAnAdmin', return_value=1, create=True):
            self.assertTrue(is_elevated())

    def test_windows_non_admin_false(self):
        from unittest.mock import patch

        from .elevation import is_elevated

        with patch('apps.core.elevation.sys.platform', 'win32'), \
                patch('apps.core.elevation.ctypes.windll.shell32.IsUserAnAdmin', return_value=0, create=True):
            self.assertFalse(is_elevated())

    def test_linux_root_true(self):
        from unittest.mock import patch

        from .elevation import is_elevated

        with patch('apps.core.elevation.sys.platform', 'linux'), \
                patch('apps.core.elevation.os.geteuid', return_value=0, create=True):
            self.assertTrue(is_elevated())

    def test_macos_non_root_false(self):
        from unittest.mock import patch

        from .elevation import is_elevated

        with patch('apps.core.elevation.sys.platform', 'darwin'), \
                patch('apps.core.elevation.os.geteuid', return_value=501, create=True):
            self.assertFalse(is_elevated())

    def test_none_on_unrecognized_platform(self):
        from unittest.mock import patch

        from .elevation import is_elevated

        with patch('apps.core.elevation.sys.platform', 'freebsd13'):
            self.assertIsNone(is_elevated())
