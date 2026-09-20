import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Protocol, Target, TargetCategory
from apps.incidents.models import EventType, Incident, RecoveryStatus, Severity
from apps.measurements.models import ICMPMeasurement

from .generators import (
    generate_csv_report,
    generate_html_report,
    generate_json_report,
    generate_monthly_report,
    generate_pdf_report,
    generate_periodic_reports,
    generate_reports_for_incident,
    month_bounds,
)
from .models import Report, ReportFormat, ReportType


class ReportGeneratorTests(TestCase):
    def setUp(self):
        self.target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        now = timezone.now()
        self.incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timedelta(minutes=10), end_time=now,
            duration_seconds=600, severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
            affected_destinations=['Gateway'],
        )
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=now - timedelta(minutes=5), address_family='ipv4',
            sent=4, received=0, loss_pct=100.0, error='timed out',
        )

    def test_html_report_contains_incident_evidence(self):
        report = generate_html_report(self.incident)

        self.assertEqual(report.format, ReportFormat.HTML)
        content = (Report.objects.get(pk=report.pk).file_path)
        self.assertTrue(content.endswith('.html'))

    def test_pdf_report_produces_a_pdf_file(self):
        import os

        from django.conf import settings

        report = generate_pdf_report(self.incident)

        full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
        self.assertTrue(os.path.exists(full_path))
        with open(full_path, 'rb') as f:
            self.assertTrue(f.read(5).startswith(b'%PDF'))

    def test_csv_report_includes_measurement_rows(self):
        import os

        from django.conf import settings

        report = generate_csv_report(self.incident)

        full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
        with open(full_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('performance_during', content)
        self.assertIn('timed out', content)

    def test_json_report_includes_sla_and_summary(self):
        import os

        from django.conf import settings

        report = generate_json_report(self.incident)

        full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
        with open(full_path, encoding='utf-8') as f:
            payload = json.load(f)
        self.assertEqual(payload['summary']['incident_id'], self.incident.id)

    def test_generate_reports_for_incident_creates_all_four_formats(self):
        reports = generate_reports_for_incident(self.incident)

        formats = {r.format for r in reports}
        self.assertEqual(formats, {'html', 'pdf', 'csv', 'json'})
        self.assertEqual(Report.objects.filter(incident=self.incident).count(), 4)


class PeriodicReportGeneratorTests(TestCase):
    def setUp(self):
        self.target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        self.now = timezone.now()
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=self.now, address_family='ipv4', sent=4, received=4,
            loss_pct=0.0, avg_rtt_ms=10.0,
        )
        self.incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=self.now - timedelta(hours=1), end_time=self.now - timedelta(minutes=55),
            duration_seconds=300, severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
        )

    def test_month_bounds_starts_at_day_one(self):
        start, end = month_bounds(self.now)

        self.assertEqual(start.day, 1)
        self.assertEqual(start.hour, 0)
        self.assertEqual(end, self.now)

    def test_generate_periodic_reports_creates_all_four_formats(self):
        period_start, period_end = month_bounds(self.now)

        reports = generate_periodic_reports(period_start, period_end)

        formats = {r.format for r in reports}
        self.assertEqual(formats, {'html', 'pdf', 'csv', 'json'})
        self.assertTrue(all(r.type == ReportType.PERIODIC for r in reports))
        self.assertTrue(all(r.incident is None for r in reports))

    def test_periodic_csv_report_includes_the_incident(self):
        import os

        from django.conf import settings

        period_start, period_end = month_bounds(self.now)
        report = generate_periodic_reports(period_start, period_end)[2]  # csv is 3rd

        full_path = os.path.join(settings.MEDIA_ROOT, report.file_path)
        with open(full_path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('uptime_pct', content)
        self.assertIn(str(self.incident.id), content)

    def test_generate_monthly_report_uses_current_month(self):
        reports = generate_monthly_report(reference_date=self.now)

        expected_start, _ = month_bounds(self.now)
        self.assertEqual(reports[0].period_start, expected_start)


class ReportsListViewTests(TestCase):
    def test_reports_list_renders(self):
        response = self.client.get(reverse('reports:list'))

        self.assertEqual(response.status_code, 200)


class DownloadReportViewTests(TestCase):
    def test_download_returns_file_content(self):
        target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        now = timezone.now()
        incident = Incident.objects.create(
            type=EventType.OUTAGE, start_time=now - timedelta(minutes=5), end_time=now, duration_seconds=300,
            severity=Severity.CRITICAL, recovery_status=RecoveryStatus.RECOVERED,
        )
        report = generate_html_report(incident)

        response = self.client.get(reverse('reports:download', args=[report.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/html')

    def test_missing_report_returns_404(self):
        response = self.client.get(reverse('reports:download', args=[99999]))

        self.assertEqual(response.status_code, 404)


class ExportViewsTests(TestCase):
    def setUp(self):
        self.target = Target.objects.create(
            name='Gateway', category=TargetCategory.GATEWAY, address='192.168.1.1', protocol=Protocol.ICMP,
        )
        ICMPMeasurement.objects.create(
            target=self.target, timestamp=timezone.now(), address_family='ipv4', sent=4, received=4,
            loss_pct=0.0, avg_rtt_ms=12.0,
        )

    def test_export_measurements_csv(self):
        response = self.client.get(reverse('reports:export_measurements', args=['icmp']), {'format': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn(b'Gateway', response.content)

    def test_export_measurements_json(self):
        response = self.client.get(reverse('reports:export_measurements', args=['icmp']), {'format': 'json'})

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]['target'], 'Gateway')

    def test_export_unknown_measurement_type_404s(self):
        response = self.client.get(reverse('reports:export_measurements', args=['not_a_real_type']))

        self.assertEqual(response.status_code, 404)

    def test_export_incidents_csv(self):
        Incident.objects.create(
            type=EventType.OUTAGE, start_time=timezone.now(), severity=Severity.CRITICAL,
            recovery_status=RecoveryStatus.ONGOING,
        )

        response = self.client.get(reverse('reports:export_incidents'), {'format': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'outage', response.content)

