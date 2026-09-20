from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Protocol, Target, TargetCategory
from apps.incidents.models import EventType, Incident, RecoveryStatus, Severity
from apps.measurements.models import ICMPMeasurement
from apps.network_state.models import ConnectivityState

from . import services


class ServicesTests(TestCase):
    def setUp(self):
        self.gateway = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )

    def test_current_state_defaults_to_online(self):
        self.assertEqual(services.current_state(), ConnectivityState.ONLINE)

    def test_latest_icmp_by_target_returns_most_recent_row(self):
        now = timezone.now()
        ICMPMeasurement.objects.create(
            target=self.gateway, timestamp=now - timedelta(minutes=5), address_family='ipv4',
            sent=4, received=4, loss_pct=0.0,
        )
        latest = ICMPMeasurement.objects.create(
            target=self.gateway, timestamp=now, address_family='ipv4', sent=4, received=4, loss_pct=0.0,
            avg_rtt_ms=12.0,
        )

        rows = services.latest_icmp_by_target()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['measurement'], latest)

    def test_uptime_pct_is_100_with_no_incidents(self):
        self.assertEqual(services.uptime_pct(hours=24), 100.0)

    def test_uptime_pct_reflects_an_incident(self):
        now = timezone.now()
        Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timedelta(hours=1), end_time=now - timedelta(minutes=54),
            duration_seconds=360, severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
        )

        self.assertLess(services.uptime_pct(hours=24), 100.0)

    def test_timeseries_returns_points_for_known_metric(self):
        now = timezone.now()
        ICMPMeasurement.objects.create(
            target=self.gateway, timestamp=now, address_family='ipv4', sent=4, received=4,
            loss_pct=0.0, avg_rtt_ms=15.0,
        )

        points = services.timeseries('latency_ms', now - timedelta(hours=1), now + timedelta(minutes=1))

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]['value'], 15.0)

    def test_timeseries_returns_empty_for_unknown_metric(self):
        self.assertEqual(services.timeseries('not_a_real_metric', timezone.now() - timedelta(hours=1), timezone.now()), [])


class ViewsTests(TestCase):
    def test_overview_page_renders(self):
        response = self.client.get(reverse('dashboard:overview'))
        self.assertEqual(response.status_code, 200)

    def test_overview_renders_with_http_target_and_no_measurements_yet(self):
        # Regression: `row.measurement.status_code|default:row.measurement.error_type` used to raise
        # VariableDoesNotExist when `row.measurement` is None (a freshly added target with no probes yet).
        Target.objects.create(
            name='HTTP Endpoint', category=TargetCategory.HTTP, address='https://example.com', protocol=Protocol.HTTPS,
        )

        response = self.client.get(reverse('dashboard:overview'))

        self.assertEqual(response.status_code, 200)

    def test_overview_shows_elevation_warning_when_not_elevated(self):
        with patch('apps.dashboard.views.is_elevated', return_value=False):
            response = self.client.get(reverse('dashboard:overview'))

        self.assertContains(response, 'Not running as Administrator')

    def test_overview_hides_elevation_warning_when_elevated(self):
        with patch('apps.dashboard.views.is_elevated', return_value=True):
            response = self.client.get(reverse('dashboard:overview'))

        self.assertNotContains(response, 'Not running as Administrator')

    def test_api_overview_returns_json(self):
        response = self.client.get(reverse('dashboard:api_overview'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], 'online')

    def test_graphs_page_renders(self):
        response = self.client.get(reverse('dashboard:graphs'))
        self.assertEqual(response.status_code, 200)

    def test_api_timeseries_returns_json(self):
        response = self.client.get(reverse('dashboard:api_timeseries'), {'metric': 'latency_ms', 'range': '1h'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['metric'], 'latency_ms')

    def test_api_timeseries_respects_custom_range(self):
        now = timezone.now()
        start = (now - timedelta(hours=2)).isoformat()
        end = now.isoformat()

        response = self.client.get(reverse('dashboard:api_timeseries'), {
            'metric': 'latency_ms', 'range': 'custom', 'start': start, 'end': end,
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['window_start'], start)
        self.assertEqual(payload['window_end'], end)

    def test_incidents_list_renders(self):
        response = self.client.get(reverse('dashboard:incidents_list'))
        self.assertEqual(response.status_code, 200)

    def test_incident_detail_renders(self):
        incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=timezone.now(), severity=Severity.CRITICAL,
            recovery_status=RecoveryStatus.ONGOING,
        )

        response = self.client.get(reverse('dashboard:incident_detail', args=[incident.id]))

        self.assertEqual(response.status_code, 200)

    def test_sla_comparison_page_renders(self):
        response = self.client.get(reverse('dashboard:sla_comparison'))
        self.assertEqual(response.status_code, 200)

    def test_baseline_comparison_page_renders_with_seeded_placeholder(self):
        response = self.client.get(reverse('dashboard:baseline_comparison'))
        self.assertEqual(response.status_code, 200)

    def test_historical_comparison_page_renders(self):
        response = self.client.get(reverse('dashboard:historical_comparison'))
        self.assertEqual(response.status_code, 200)


class ComparisonServicesTests(TestCase):
    def test_baseline_comparison_rows_uses_seeded_placeholder(self):
        target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        ICMPMeasurement.objects.create(
            target=target, timestamp=timezone.now(), address_family='ipv4', sent=4, received=4,
            loss_pct=0.0, avg_rtt_ms=20.0,
        )

        rows = services.baseline_comparison_rows(hours=24)

        latency_row = next(r for r in rows if r['metric'] == 'latency_ms')
        self.assertIsNotNone(latency_row['comparison'])

    def test_historical_comparison_returns_current_and_previous(self):
        result = services.historical_comparison(hours=24)

        self.assertIn('current', result)
        self.assertIn('previous', result)
        self.assertEqual(result['current']['uptime_pct'], 100.0)

    def test_sla_comparison_rows_returns_enabled_rules_only(self):
        from apps.sla.models import SLAMetric, SLAOperator, SLARule

        SLARule.objects.create(
            name='Enabled rule', metric=SLAMetric.LATENCY_MS, operator=SLAOperator.GT, threshold=100.0,
            measurement_window_seconds=3600,
        )
        SLARule.objects.create(
            name='Disabled rule', metric=SLAMetric.LATENCY_MS, operator=SLAOperator.GT, threshold=100.0,
            measurement_window_seconds=3600, enabled=False,
        )

        rows = services.sla_comparison_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['rule'].name, 'Enabled rule')

