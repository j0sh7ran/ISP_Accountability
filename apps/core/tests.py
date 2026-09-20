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


class AdminCSVImportExportTests(TestCase):
    """Covers apps/core/admin_csv.py's CSVImportExportMixin via TargetAdmin/ScheduleConfigAdmin."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        admin_user = user_model.objects.create_superuser('csvadmin', 'csvadmin@example.com', 'password123!')
        self.client.force_login(admin_user)

    def test_export_as_csv_action(self):
        from django.urls import reverse

        target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )

        response = self.client.post(reverse('admin:core_target_changelist'), {
            'action': 'export_as_csv', '_selected_action': [str(target.pk)],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode()
        self.assertIn('Gateway', content)
        self.assertIn('192.168.1.1', content)

    def test_import_csv_creates_a_new_row(self):
        import io

        from django.urls import reverse

        csv_content = (
            'name,category,address,address_family,protocol,port,enabled\n'
            'Home Router,gateway,192.168.0.1,ipv4,icmp,,true\n'
        )
        upload = io.BytesIO(csv_content.encode())
        upload.name = 'targets.csv'

        response = self.client.post(reverse('admin:core_target_import_csv'), {'csv_file': upload})

        self.assertEqual(response.status_code, 302)
        target = Target.objects.get(name='Home Router')
        self.assertEqual(target.address, '192.168.0.1')
        self.assertTrue(target.enabled)

    def test_import_csv_updates_existing_row_by_key_field(self):
        import io

        from django.urls import reverse

        Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='old-address',
            protocol=Protocol.ICMP, enabled=True,
        )
        csv_content = (
            'name,category,address,address_family,protocol,port,enabled\n'
            'Gateway,gateway,10.0.0.1,ipv4,icmp,,false\n'
        )
        upload = io.BytesIO(csv_content.encode())
        upload.name = 'targets.csv'

        self.client.post(reverse('admin:core_target_import_csv'), {'csv_file': upload})

        self.assertEqual(Target.objects.count(), 1)
        target = Target.objects.get(name='Gateway')
        self.assertEqual(target.address, '10.0.0.1')
        self.assertFalse(target.enabled)

    def test_import_csv_reports_row_errors_without_failing_the_whole_import(self):
        import io

        from django.urls import reverse

        csv_content = (
            'task_type,interval_seconds,enabled\n'
            'icmp,not-a-number,true\n'
            'dns,300,true\n'
        )
        upload = io.BytesIO(csv_content.encode())
        upload.name = 'schedules.csv'

        response = self.client.post(reverse('admin:core_scheduleconfig_import_csv'), {'csv_file': upload})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ScheduleConfig.objects.get(task_type='dns').interval_seconds, 300)
