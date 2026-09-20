from unittest.mock import patch

from django.test import TestCase

from apps.core.models import (
    MeasurementCategory,
    OnDemandTestRequest,
    OnDemandTestStatus,
    Protocol,
    ScheduleConfig,
    Target,
    TargetCategory,
)
from apps.measurements.models import (
    BufferbloatTest,
    DNSMeasurement,
    HTTPMeasurement,
    ICMPMeasurement,
    InterfaceMetric,
    MTUTestResult,
    RouteChangeEvent,
    RouteTestRun,
    TCPMeasurement,
    ThroughputMeasurement,
)

from .jobs import (
    run_bufferbloat_job,
    run_dns_job,
    run_http_job,
    run_icmp_job,
    run_interface_job,
    run_mtu_job,
    run_route_job,
    run_tcp_job,
    run_throughput_job,
)


class RunICMPJobTests(TestCase):
    """No real network access — the probe function itself is mocked."""

    @patch('apps.worker.jobs.run_icmp_probe')
    def test_probes_every_enabled_icmp_target_and_records_a_row(self, mock_probe):
        mock_probe.return_value = {
            'sent': 4, 'received': 4, 'loss_pct': 0.0, 'min_rtt_ms': 10.0, 'avg_rtt_ms': 12.0,
            'median_rtt_ms': 12.0, 'max_rtt_ms': 14.0, 'p95_rtt_ms': 14.0, 'p99_rtt_ms': 14.0,
            'jitter_ms': 1.0, 'error': '',
        }
        gateway = Target.objects.create(
            name='Default Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1',
            protocol=Protocol.ICMP,
        )
        Target.objects.create(
            name='Disabled Target', category=TargetCategory.INTERNET, address='198.51.100.1',
            protocol=Protocol.ICMP, enabled=False,
        )

        run_icmp_job()

        self.assertEqual(ICMPMeasurement.objects.count(), 1)
        self.assertEqual(ICMPMeasurement.objects.get().target, gateway)
        mock_probe.assert_called_once_with('192.168.1.1')

    @patch('apps.worker.jobs.run_icmp_probe')
    def test_updates_schedule_config_last_run(self, mock_probe):
        from apps.core.models import MeasurementCategory, ScheduleConfig

        mock_probe.return_value = {
            'sent': 4, 'received': 0, 'loss_pct': 100.0, 'min_rtt_ms': None, 'avg_rtt_ms': None,
            'median_rtt_ms': None, 'max_rtt_ms': None, 'p95_rtt_ms': None, 'p99_rtt_ms': None,
            'jitter_ms': None, 'error': 'timed out',
        }
        Target.objects.create(
            name='Default Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1',
            protocol=Protocol.ICMP,
        )

        run_icmp_job()

        schedule = ScheduleConfig.objects.get(task_type=MeasurementCategory.ICMP)
        self.assertIsNotNone(schedule.last_run)

    @patch('apps.worker.jobs.evaluate_and_log_state')
    @patch('apps.worker.jobs.run_icmp_probe')
    def test_triggers_state_evaluation(self, mock_probe, mock_evaluate):
        mock_probe.return_value = {
            'sent': 4, 'received': 4, 'loss_pct': 0.0, 'min_rtt_ms': 10.0, 'avg_rtt_ms': 12.0,
            'median_rtt_ms': 12.0, 'max_rtt_ms': 14.0, 'p95_rtt_ms': 14.0, 'p99_rtt_ms': 14.0,
            'jitter_ms': 1.0, 'error': '',
        }
        Target.objects.create(
            name='Default Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1',
            protocol=Protocol.ICMP,
        )

        run_icmp_job()

        mock_evaluate.assert_called_once()


class RunDNSJobTests(TestCase):
    @patch('apps.worker.jobs.run_dns_probe')
    def test_probes_every_enabled_dns_target(self, mock_probe):
        mock_probe.return_value = {'resolution_time_ms': 12.0, 'result_type': 'success', 'resolved_ip': '1.2.3.4'}
        Target.objects.create(
            name='Cloudflare DNS', category=TargetCategory.DNS, address='1.1.1.1', protocol=Protocol.DNS,
        )

        run_dns_job()

        self.assertEqual(DNSMeasurement.objects.count(), 1)
        mock_probe.assert_called_once_with('1.1.1.1', 'www.example.com')


class RunHTTPJobTests(TestCase):
    @patch('apps.worker.jobs.run_http_probe')
    def test_probes_every_enabled_http_target(self, mock_probe):
        mock_probe.return_value = {
            'dns_time_ms': 5.0, 'connect_time_ms': 10.0, 'tls_time_ms': 20.0, 'ttfb_ms': 30.0,
            'total_time_ms': 40.0, 'status_code': 200, 'redirect_count': 0, 'error_type': '',
        }
        Target.objects.create(
            name='Example site', category=TargetCategory.HTTP, address='https://example.com/',
            protocol=Protocol.HTTPS,
        )

        run_http_job()

        self.assertEqual(HTTPMeasurement.objects.count(), 1)


class RunTCPJobTests(TestCase):
    @patch('apps.worker.jobs.run_tcp_probe')
    def test_probes_target_with_port_configured(self, mock_probe):
        mock_probe.return_value = {'success': True, 'error_type': '', 'connect_time_ms': 5.0}
        Target.objects.create(
            name='Mail server', category=TargetCategory.CUSTOM, address='10.0.0.5', protocol=Protocol.TCP,
            port=25,
        )

        run_tcp_job()

        self.assertEqual(TCPMeasurement.objects.count(), 1)
        mock_probe.assert_called_once_with('10.0.0.5', 25)

    @patch('apps.worker.jobs.run_tcp_probe')
    def test_skips_target_without_port(self, mock_probe):
        Target.objects.create(
            name='No port configured', category=TargetCategory.CUSTOM, address='10.0.0.6',
            protocol=Protocol.TCP,
        )

        run_tcp_job()

        mock_probe.assert_not_called()
        self.assertEqual(TCPMeasurement.objects.count(), 0)


class RunInterfaceJobTests(TestCase):
    @patch('apps.worker.jobs.collect_interface_metrics')
    def test_records_one_row_per_interface(self, mock_collect):
        mock_collect.return_value = [{
            'interface_name': 'Ethernet', 'state': 'up', 'link_speed_mbps': 1000,
            'bytes_sent': 1, 'bytes_received': 2, 'packets_sent': 1, 'packets_received': 2,
            'errors_in': 0, 'errors_out': 0, 'discards': 0,
        }]

        run_interface_job()

        self.assertEqual(InterfaceMetric.objects.count(), 1)


class RunRouteJobTests(TestCase):
    @patch('apps.worker.jobs.run_traceroute')
    def test_first_run_creates_no_change_event(self, mock_traceroute):
        mock_traceroute.return_value = [
            {'hop_number': 1, 'ip_address': '192.168.1.1', 'hostname': '', 'rtt_ms': 1.0, 'timeout': False},
        ]
        Target.objects.create(
            name='Internet endpoint', category=TargetCategory.INTERNET, address='93.184.216.34',
            protocol=Protocol.ICMP,
        )

        run_route_job()

        self.assertEqual(RouteTestRun.objects.count(), 1)
        self.assertEqual(RouteChangeEvent.objects.count(), 0)

    @patch('apps.worker.jobs.run_traceroute')
    def test_changed_first_hop_creates_change_event(self, mock_traceroute):
        target = Target.objects.create(
            name='Internet endpoint', category=TargetCategory.INTERNET, address='93.184.216.34',
            protocol=Protocol.ICMP,
        )
        mock_traceroute.return_value = [
            {'hop_number': 1, 'ip_address': '192.168.1.1', 'hostname': '', 'rtt_ms': 1.0, 'timeout': False},
        ]
        run_route_job()

        mock_traceroute.return_value = [
            {'hop_number': 1, 'ip_address': '192.168.1.254', 'hostname': '', 'rtt_ms': 1.0, 'timeout': False},
        ]
        run_route_job()

        self.assertEqual(RouteTestRun.objects.filter(target=target).count(), 2)
        self.assertEqual(RouteChangeEvent.objects.count(), 1)
        self.assertTrue(RouteChangeEvent.objects.get().first_hop_changed)

    @patch('apps.worker.jobs.run_traceroute')
    def test_route_change_also_creates_an_incidents_event(self, mock_traceroute):
        from apps.incidents.models import Event, EventType

        Target.objects.create(
            name='Internet endpoint', category=TargetCategory.INTERNET, address='93.184.216.34',
            protocol=Protocol.ICMP,
        )
        mock_traceroute.return_value = [
            {'hop_number': 1, 'ip_address': '192.168.1.1', 'hostname': '', 'rtt_ms': 1.0, 'timeout': False},
        ]
        run_route_job()
        mock_traceroute.return_value = [
            {'hop_number': 1, 'ip_address': '192.168.1.254', 'hostname': '', 'rtt_ms': 1.0, 'timeout': False},
        ]
        run_route_job()

        self.assertEqual(Event.objects.filter(type=EventType.ROUTE_CHANGE).count(), 1)


class RunMTUJobTests(TestCase):
    @patch('apps.worker.jobs.run_mtu_probe')
    def test_probes_representative_targets(self, mock_probe):
        mock_probe.return_value = {
            'largest_successful_size': 1400, 'df_behavior': 'df_honored_fragmentation_needed',
            'pmtud_response': 'fragmentation_needed', 'failure_threshold': 1401,
        }
        Target.objects.create(
            name='Internet endpoint', category=TargetCategory.INTERNET, address='93.184.216.34',
            protocol=Protocol.ICMP,
        )

        run_mtu_job()

        self.assertEqual(MTUTestResult.objects.count(), 1)


class RunThroughputJobTests(TestCase):
    @patch('apps.worker.jobs.run_throughput_probe')
    def test_does_nothing_without_request_or_schedule_enabled(self, mock_probe):
        run_throughput_job()

        mock_probe.assert_not_called()
        self.assertEqual(ThroughputMeasurement.objects.count(), 0)

    @patch('apps.worker.jobs.run_throughput_probe')
    def test_runs_and_completes_a_pending_on_demand_request(self, mock_probe):
        mock_probe.return_value = {'mbps_down': 100.0, 'mbps_up': 20.0, 'duration_s': 5.0, 'endpoint': 'x', 'error': ''}
        request = OnDemandTestRequest.objects.create(task_type=MeasurementCategory.THROUGHPUT)

        run_throughput_job()

        request.refresh_from_db()
        self.assertEqual(request.status, OnDemandTestStatus.COMPLETED)
        self.assertEqual(ThroughputMeasurement.objects.count(), 1)


class RunBufferbloatJobTests(TestCase):
    @patch('apps.worker.jobs.run_bufferbloat_probe')
    def test_skips_without_gateway_target(self, mock_probe):
        request = OnDemandTestRequest.objects.create(task_type=MeasurementCategory.BUFFERBLOAT)

        run_bufferbloat_job()

        mock_probe.assert_not_called()
        self.assertEqual(BufferbloatTest.objects.count(), 0)
        request.refresh_from_db()
        self.assertEqual(request.status, OnDemandTestStatus.FAILED)

    @patch('apps.worker.jobs.run_bufferbloat_probe')
    def test_runs_when_gateway_target_and_request_present(self, mock_probe):
        mock_probe.return_value = {
            'baseline_rtt_ms': 10.0, 'loaded_rtt_download_ms': None, 'loaded_rtt_upload_ms': None,
            'loaded_rtt_bidirectional_ms': 50.0, 'loss_during_load_pct': 0.0,
            'throughput_during_load_mbps': 90.0, 'recovery_time_s': 1.0, 'classification': 'moderate',
        }
        Target.objects.create(
            name='Default Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1',
            protocol=Protocol.ICMP,
        )
        OnDemandTestRequest.objects.create(task_type=MeasurementCategory.BUFFERBLOAT)

        run_bufferbloat_job()

        self.assertEqual(BufferbloatTest.objects.count(), 1)

    @patch('apps.worker.jobs.run_bufferbloat_probe')
    def test_severe_result_also_creates_an_incidents_event(self, mock_probe):
        from apps.incidents.models import Event, EventType

        mock_probe.return_value = {
            'baseline_rtt_ms': 10.0, 'loaded_rtt_download_ms': None, 'loaded_rtt_upload_ms': None,
            'loaded_rtt_bidirectional_ms': 200.0, 'loss_during_load_pct': 2.0,
            'throughput_during_load_mbps': 90.0, 'recovery_time_s': 1.0, 'classification': 'severe',
        }
        Target.objects.create(
            name='Default Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1',
            protocol=Protocol.ICMP,
        )
        OnDemandTestRequest.objects.create(task_type=MeasurementCategory.BUFFERBLOAT)

        run_bufferbloat_job()

        self.assertEqual(Event.objects.filter(type=EventType.BUFFERBLOAT).count(), 1)


class RunMonthlyReportJobTests(TestCase):
    def test_generates_a_periodic_report_for_the_current_month(self):
        from apps.reports.models import Report, ReportType

        from .jobs import run_monthly_report_job

        run_monthly_report_job()

        self.assertEqual(Report.objects.filter(type=ReportType.PERIODIC).count(), 4)



