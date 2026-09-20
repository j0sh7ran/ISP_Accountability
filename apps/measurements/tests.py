from unittest.mock import MagicMock, patch

import dns.exception
import dns.resolver
import requests
from django.test import TestCase
from django.utils import timezone
from icmplib import ICMPLibError

from apps.core.models import AddressFamily, Protocol, Target, TargetCategory

from .models import ICMPMeasurement
from .probes.bufferbloat import run_bufferbloat_probe
from .probes.dns import run_dns_probe
from .probes.http import run_http_probe
from .probes.icmp import run_icmp_probe
from .probes.interface import collect_interface_metrics
from .probes.mtu import run_mtu_probe
from .probes.route import parse_tracert_output
from .probes.tcp import run_tcp_probe
from .probes.throughput import run_throughput_probe


class ICMPProbeTests(TestCase):
    """No real network access — icmplib.ping is mocked (see docs/PHASES.md testing strategy)."""

    @patch('apps.measurements.probes.icmp.icmp_ping')
    def test_successful_probe_summarizes_rtts(self, mock_ping):
        mock_ping.return_value = MagicMock(
            packets_sent=4,
            packets_received=4,
            packet_loss=0.0,
            min_rtt=10.0,
            avg_rtt=12.5,
            max_rtt=15.0,
            jitter=1.2,
            rtts=[10.0, 11.0, 15.0, 14.0],
        )

        result = run_icmp_probe('192.168.1.1')

        self.assertEqual(result['sent'], 4)
        self.assertEqual(result['received'], 4)
        self.assertEqual(result['loss_pct'], 0.0)
        self.assertEqual(result['median_rtt_ms'], 12.5)
        self.assertEqual(result['error'], '')

    @patch('apps.measurements.probes.icmp.icmp_ping')
    def test_failed_probe_returns_error_result_instead_of_raising(self, mock_ping):
        mock_ping.side_effect = ICMPLibError('no permission to create raw socket')

        result = run_icmp_probe('192.168.1.1')

        self.assertEqual(result['received'], 0)
        self.assertEqual(result['loss_pct'], 100.0)
        self.assertIn('permission', result['error'])


class ICMPMeasurementModelTests(TestCase):
    def test_can_store_probe_result_against_a_target(self):
        target = Target.objects.create(
            name='Default Gateway',
            category=TargetCategory.GATEWAY,
            address='192.168.1.1',
            protocol=Protocol.ICMP,
        )

        measurement = ICMPMeasurement.objects.create(
            target=target,
            timestamp=timezone.now(),
            address_family=AddressFamily.IPV4,
            sent=4,
            received=4,
            loss_pct=0.0,
            avg_rtt_ms=12.5,
        )

        self.assertEqual(target.icmp_measurements.count(), 1)
        self.assertIn(target.name, str(measurement))


class DNSProbeTests(TestCase):
    @patch('apps.measurements.probes.dns.dns.resolver.Resolver.resolve')
    def test_successful_resolution(self, mock_resolve):
        mock_resolve.return_value = [MagicMock(to_text=lambda: '93.184.216.34')]

        result = run_dns_probe('1.1.1.1', 'example.com')

        self.assertEqual(result['result_type'], 'success')
        self.assertEqual(result['resolved_ip'], '93.184.216.34')

    @patch('apps.measurements.probes.dns.dns.resolver.Resolver.resolve')
    def test_nxdomain(self, mock_resolve):
        mock_resolve.side_effect = dns.resolver.NXDOMAIN()

        result = run_dns_probe('1.1.1.1', 'does-not-exist.invalid')

        self.assertEqual(result['result_type'], 'nxdomain')

    @patch('apps.measurements.probes.dns.dns.resolver.Resolver.resolve')
    def test_timeout(self, mock_resolve):
        mock_resolve.side_effect = dns.exception.Timeout()

        result = run_dns_probe('1.1.1.1', 'example.com')

        self.assertEqual(result['result_type'], 'timeout')


class HTTPProbeTests(TestCase):
    @patch('apps.measurements.probes.http.requests.get')
    @patch('apps.measurements.probes.http.socket.create_connection')
    @patch('apps.measurements.probes.http.socket.getaddrinfo')
    def test_successful_plain_http_request(self, mock_getaddrinfo, mock_create_connection, mock_get):
        mock_getaddrinfo.return_value = [MagicMock()]
        mock_create_connection.return_value = MagicMock()
        mock_response = MagicMock(status_code=200, history=[])
        mock_response.elapsed.total_seconds.return_value = 0.05
        mock_get.return_value = mock_response

        result = run_http_probe('http://example.com/')

        self.assertEqual(result['status_code'], 200)
        self.assertEqual(result['error_type'], '')

    @patch('apps.measurements.probes.http.socket.getaddrinfo')
    def test_dns_failure(self, mock_getaddrinfo):
        import socket
        mock_getaddrinfo.side_effect = socket.gaierror('name not known')

        result = run_http_probe('http://does-not-exist.invalid/')

        self.assertEqual(result['error_type'], 'dns_error')

    @patch('apps.measurements.probes.http.requests.get')
    @patch('apps.measurements.probes.http.socket.create_connection')
    @patch('apps.measurements.probes.http.socket.getaddrinfo')
    def test_request_timeout(self, mock_getaddrinfo, mock_create_connection, mock_get):
        mock_getaddrinfo.return_value = [MagicMock()]
        mock_create_connection.return_value = MagicMock()
        mock_get.side_effect = requests.Timeout()

        result = run_http_probe('http://example.com/')

        self.assertEqual(result['error_type'], 'timeout')


class TCPProbeTests(TestCase):
    @patch('apps.measurements.probes.tcp.socket.create_connection')
    def test_successful_connection(self, mock_create_connection):
        mock_create_connection.return_value = MagicMock()

        result = run_tcp_probe('192.168.1.1', 80)

        self.assertTrue(result['success'])
        self.assertEqual(result['error_type'], '')

    @patch('apps.measurements.probes.tcp.socket.create_connection')
    def test_connection_refused(self, mock_create_connection):
        mock_create_connection.side_effect = ConnectionRefusedError()

        result = run_tcp_probe('192.168.1.1', 80)

        self.assertFalse(result['success'])
        self.assertEqual(result['error_type'], 'refused')


class InterfaceProbeTests(TestCase):
    @patch('apps.measurements.probes.interface.psutil.net_if_stats')
    @patch('apps.measurements.probes.interface.psutil.net_io_counters')
    def test_collects_one_row_per_interface(self, mock_io_counters, mock_if_stats):
        mock_io_counters.return_value = {
            'Ethernet': MagicMock(bytes_sent=100, bytes_recv=200, packets_sent=1, packets_recv=2,
                                   errin=0, errout=0, dropin=0, dropout=0),
        }
        mock_if_stats.return_value = {'Ethernet': MagicMock(isup=True, speed=1000)}

        results = collect_interface_metrics()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['interface_name'], 'Ethernet')
        self.assertEqual(results[0]['state'], 'up')
        self.assertEqual(results[0]['link_speed_mbps'], 1000)


class RouteParserTests(TestCase):
    def test_parses_successful_hop(self):
        output = '  1     1 ms     1 ms     1 ms  192.168.1.1\n'

        hops = parse_tracert_output(output)

        self.assertEqual(hops, [{
            'hop_number': 1, 'ip_address': '192.168.1.1', 'hostname': '', 'rtt_ms': 1.0, 'timeout': False,
        }])

    def test_parses_timed_out_hop(self):
        output = '  2     *        *        *     Request timed out.\n'

        hops = parse_tracert_output(output)

        self.assertEqual(hops, [{
            'hop_number': 2, 'ip_address': '', 'hostname': '', 'rtt_ms': None, 'timeout': True,
        }])

    def test_ignores_non_hop_lines(self):
        output = 'Tracing route to example.com [93.184.216.34]\nover a maximum of 30 hops:\n\nTrace complete.\n'

        hops = parse_tracert_output(output)

        self.assertEqual(hops, [])


class MTUProbeTests(TestCase):
    @patch('apps.measurements.probes.mtu._ping_df')
    def test_binary_search_finds_boundary(self, mock_ping_df):
        # Anything <= 1400 succeeds, anything above fails with a fragmentation message.
        def fake_ping(address, size, timeout_ms=2000):
            if size <= 1400:
                return True, 'Reply from 1.2.3.4: bytes=1400 time=1ms TTL=64'
            return False, 'Packet needs to be fragmented but DF set.'

        mock_ping_df.side_effect = fake_ping

        result = run_mtu_probe('1.2.3.4', low=1200, high=1500)

        self.assertEqual(result['largest_successful_size'], 1400)
        self.assertEqual(result['df_behavior'], 'df_honored_fragmentation_needed')


class ThroughputProbeTests(TestCase):
    @patch('apps.measurements.probes.throughput.speedtest.Speedtest')
    def test_successful_test_reports_mbps(self, mock_speedtest_cls):
        instance = mock_speedtest_cls.return_value
        instance.download.return_value = 100_000_000
        instance.upload.return_value = 20_000_000
        instance.results.server = {'host': 'speedtest.example.com'}

        result = run_throughput_probe('bidirectional')

        self.assertAlmostEqual(result['mbps_down'], 100.0)
        self.assertAlmostEqual(result['mbps_up'], 20.0)
        self.assertEqual(result['error'], '')

    @patch('apps.measurements.probes.throughput.speedtest.Speedtest')
    def test_failure_returns_error_result_instead_of_raising(self, mock_speedtest_cls):
        mock_speedtest_cls.side_effect = Exception('could not reach speedtest infrastructure')

        result = run_throughput_probe('bidirectional')

        self.assertIsNone(result['mbps_down'])
        self.assertIn('speedtest', result['error'])


class BufferbloatProbeTests(TestCase):
    @patch('apps.measurements.probes.bufferbloat.run_throughput_probe')
    @patch('apps.measurements.probes.bufferbloat.run_icmp_probe')
    def test_classifies_severe_latency_increase(self, mock_icmp, mock_throughput):
        # baseline, loaded, recovery — three sequential run_icmp_probe calls.
        mock_icmp.side_effect = [
            {'avg_rtt_ms': 10.0, 'loss_pct': 0.0},
            {'avg_rtt_ms': 150.0, 'loss_pct': 1.0},
            {'avg_rtt_ms': 12.0, 'loss_pct': 0.0},
        ]
        mock_throughput.return_value = {'mbps_down': 50.0, 'mbps_up': 10.0, 'error': ''}

        result = run_bufferbloat_probe('192.168.1.1')

        self.assertEqual(result['baseline_rtt_ms'], 10.0)
        self.assertEqual(result['loaded_rtt_bidirectional_ms'], 150.0)
        self.assertEqual(result['classification'], 'severe')


class AggregationTests(TestCase):
    def setUp(self):
        self.target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )

    def test_aggregate_hour_computes_stats_per_target(self):
        from apps.measurements.aggregation import aggregate_hour

        hour_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        for i, rtt in enumerate([10.0, 20.0, 30.0]):
            ICMPMeasurement.objects.create(
                target=self.target, timestamp=hour_start + timezone.timedelta(minutes=i * 10),
                address_family='ipv4', sent=4, received=4, loss_pct=0.0, avg_rtt_ms=rtt,
            )

        results = aggregate_hour('latency_ms', hour_start)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].avg_value, 20.0)
        self.assertEqual(results[0].min_value, 10.0)
        self.assertEqual(results[0].max_value, 30.0)
        self.assertEqual(results[0].sample_count, 3)

    def test_aggregate_hour_is_idempotent(self):
        from apps.measurements.aggregation import aggregate_hour
        from apps.measurements.models import HourlyAggregate

        hour_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=hour_start, address_family='ipv4', sent=4, received=4,
            loss_pct=0.0, avg_rtt_ms=10.0,
        )

        aggregate_hour('latency_ms', hour_start)
        aggregate_hour('latency_ms', hour_start)

        self.assertEqual(HourlyAggregate.objects.count(), 1)

    def test_aggregate_day_rolls_up_hourly_rows(self):
        from apps.measurements.aggregation import aggregate_day
        from apps.measurements.models import HourlyAggregate

        day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        HourlyAggregate.objects.create(
            target=self.target, metric='latency_ms', period_start=day_start,
            avg_value=10.0, min_value=8.0, max_value=12.0, p95_value=11.0, sample_count=10,
        )
        HourlyAggregate.objects.create(
            target=self.target, metric='latency_ms', period_start=day_start + timezone.timedelta(hours=1),
            avg_value=20.0, min_value=15.0, max_value=25.0, p95_value=24.0, sample_count=10,
        )

        results = aggregate_day('latency_ms', day_start)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].avg_value, 15.0)
        self.assertEqual(results[0].min_value, 8.0)
        self.assertEqual(results[0].max_value, 25.0)
        self.assertEqual(results[0].sample_count, 20)


class RetentionTests(TestCase):
    def test_enforce_retention_deletes_only_old_raw_rows(self):
        from apps.core.models import MeasurementCategory, RetentionPolicy
        from apps.measurements.retention import enforce_retention

        target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        now = timezone.now()
        old = ICMPMeasurement.objects.create(
            target=target, timestamp=now - timezone.timedelta(days=10), address_family='ipv4',
            sent=4, received=4, loss_pct=0.0,
        )
        recent = ICMPMeasurement.objects.create(
            target=target, timestamp=now - timezone.timedelta(hours=1), address_family='ipv4',
            sent=4, received=4, loss_pct=0.0,
        )
        RetentionPolicy.objects.filter(data_type=MeasurementCategory.ICMP).update(raw_retention_days=7)

        enforce_retention(now=now)

        self.assertFalse(ICMPMeasurement.objects.filter(pk=old.pk).exists())
        self.assertTrue(ICMPMeasurement.objects.filter(pk=recent.pk).exists())

    def test_indefinite_policy_deletes_nothing(self):
        from apps.measurements.retention import enforce_retention

        target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        now = timezone.now()
        ICMPMeasurement.objects.create(
            target=target, timestamp=now - timezone.timedelta(days=3650), address_family='ipv4',
            sent=4, received=4, loss_pct=0.0,
        )

        enforce_retention(now=now)

        self.assertEqual(ICMPMeasurement.objects.count(), 1)

    def test_incidents_are_never_touched_by_retention(self):
        from apps.core.models import MeasurementCategory, RetentionPolicy
        from apps.incidents.models import EventType, Incident, RecoveryStatus, Severity
        from apps.measurements.retention import enforce_retention

        now = timezone.now()
        Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timezone.timedelta(days=3650),
            end_time=now - timezone.timedelta(days=3650), duration_seconds=60,
            severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
        )
        RetentionPolicy.objects.filter(data_type=MeasurementCategory.ICMP).update(raw_retention_days=1)

        enforce_retention(now=now)

        self.assertEqual(Incident.objects.count(), 1)


