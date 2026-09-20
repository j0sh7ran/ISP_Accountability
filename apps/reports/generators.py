"""Outage report generation (§26/§27) — HTML/PDF/CSV/JSON, all rendered fully offline.

`build_outage_report_context` gathers evidence into one dict; the HTML/PDF renderers share a single
Django template so the two formats never drift apart, while CSV/JSON serialize the same context.
"""
import csv
import io
import json
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from apps.measurements.models import ICMPMeasurement
from apps.incidents.models import Incident
from apps.sla.models import SLAEvaluation

from .models import Report, ReportFormat, ReportType

EVIDENCE_WINDOW = timezone.timedelta(minutes=10)


def build_outage_report_context(incident):
    """Gathers evidence for one incident into a single, template-agnostic dict."""
    start = incident.start_time
    end = incident.end_time or timezone.now()

    before_qs = ICMPMeasurement.objects.filter(
        timestamp__gte=start - EVIDENCE_WINDOW, timestamp__lt=start
    ).order_by('timestamp')
    during_qs = ICMPMeasurement.objects.filter(timestamp__gte=start, timestamp__lte=end).order_by('timestamp')
    after_qs = ICMPMeasurement.objects.filter(
        timestamp__gt=end, timestamp__lte=end + EVIDENCE_WINDOW
    ).order_by('timestamp')

    return {
        'incident': incident,
        'summary': {
            'incident_id': incident.id,
            'start': start,
            'end': incident.end_time,
            'duration_seconds': incident.duration_seconds,
            'recovery_status': incident.recovery_status,
            'affected_destinations': incident.affected_destinations,
            'affected_tests': incident.affected_tests,
        },
        'events': list(incident.events.order_by('start_time')),
        'performance_before': list(before_qs),
        'performance_during': list(during_qs),
        'performance_after': list(after_qs),
        'sla_evaluations': list(incident.sla_evaluations.order_by('-window_end')),
        'generated_at': timezone.now(),
    }


def render_outage_report_html(incident):
    context = build_outage_report_context(incident)
    return render_to_string('reports/outage_report.html', context)


def _reports_dir():
    reports_dir = Path(settings.MEDIA_ROOT) / 'reports'
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _write_file(prefix, extension, content, mode='w', encoding='utf-8'):
    filename = f'{prefix}.{extension}'
    path = _reports_dir() / filename
    if mode == 'wb':
        path.write_bytes(content)
    else:
        path.write_text(content, encoding=encoding)
    return str(Path('reports') / filename)


def generate_html_report(incident):
    html = render_outage_report_html(incident)
    file_path = _write_file(f'incident-{incident.id}-outage-report', 'html', html)
    return Report.objects.create(
        incident=incident, type=ReportType.OUTAGE, format=ReportFormat.HTML,
        file_path=file_path, period_start=incident.start_time, period_end=incident.end_time or timezone.now(),
    )


def generate_pdf_report(incident):
    html = render_outage_report_html(incident)
    buffer = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buffer, encoding='utf-8')
    file_path = _write_file(f'incident-{incident.id}-outage-report', 'pdf', buffer.getvalue(), mode='wb')
    return Report.objects.create(
        incident=incident, type=ReportType.OUTAGE, format=ReportFormat.PDF,
        file_path=file_path, period_start=incident.start_time, period_end=incident.end_time or timezone.now(),
    )


def generate_csv_report(incident):
    context = build_outage_report_context(incident)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['section', 'timestamp', 'target', 'loss_pct', 'avg_rtt_ms', 'error'])
    for section in ('performance_before', 'performance_during', 'performance_after'):
        for m in context[section]:
            writer.writerow([section, m.timestamp.isoformat(), m.target.name, m.loss_pct, m.avg_rtt_ms, m.error])
    file_path = _write_file(f'incident-{incident.id}-outage-report', 'csv', buffer.getvalue())
    return Report.objects.create(
        incident=incident, type=ReportType.OUTAGE, format=ReportFormat.CSV,
        file_path=file_path, period_start=incident.start_time, period_end=incident.end_time or timezone.now(),
    )


def _measurement_to_dict(m):
    return {
        'timestamp': m.timestamp.isoformat(), 'target': m.target.name, 'loss_pct': m.loss_pct,
        'avg_rtt_ms': m.avg_rtt_ms, 'error': m.error,
    }


def generate_json_report(incident):
    context = build_outage_report_context(incident)
    payload = {
        'summary': {
            **{k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in context['summary'].items()},
        },
        'performance_before': [_measurement_to_dict(m) for m in context['performance_before']],
        'performance_during': [_measurement_to_dict(m) for m in context['performance_during']],
        'performance_after': [_measurement_to_dict(m) for m in context['performance_after']],
        'sla_evaluations': [
            {
                'rule': e.rule.name, 'status': e.status, 'observed_value': e.observed_value,
                'threshold_value': e.threshold_value,
            }
            for e in context['sla_evaluations']
        ],
        'generated_at': context['generated_at'].isoformat(),
    }
    file_path = _write_file(f'incident-{incident.id}-outage-report', 'json', json.dumps(payload, indent=2))
    return Report.objects.create(
        incident=incident, type=ReportType.OUTAGE, format=ReportFormat.JSON,
        file_path=file_path, period_start=incident.start_time, period_end=incident.end_time or timezone.now(),
    )


def generate_reports_for_incident(incident):
    """Auto-called when an incident closes (§18/§26) — produces all four formats at once."""
    return [
        generate_html_report(incident),
        generate_pdf_report(incident),
        generate_csv_report(incident),
        generate_json_report(incident),
    ]


def month_bounds(reference_date):
    """(start, end) for the calendar month containing `reference_date` — `end` is `reference_date`
    itself (a monthly report is generated at month-end, not after the month has fully elapsed).
    """
    start = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, reference_date


def build_periodic_report_context(period_start, period_end):
    """Gathers a whole-period summary (§27/§28 style stats, not single-incident evidence)."""
    from apps.dashboard.services import period_stats

    incidents = list(Incident.objects.filter(
        start_time__gte=period_start, start_time__lt=period_end,
    ).order_by('start_time'))
    sla_evaluations = list(SLAEvaluation.objects.filter(
        window_start__gte=period_start, window_end__lte=period_end,
    ).order_by('window_start'))
    return {
        'period_start': period_start,
        'period_end': period_end,
        'stats': period_stats(period_start, period_end),
        'incidents': incidents,
        'sla_evaluations': sla_evaluations,
        'generated_at': timezone.now(),
    }


def render_periodic_report_html(period_start, period_end):
    context = build_periodic_report_context(period_start, period_end)
    return render_to_string('reports/periodic_report.html', context)


def generate_html_periodic_report(period_start, period_end):
    html = render_periodic_report_html(period_start, period_end)
    file_path = _write_file(f'periodic-{period_start:%Y-%m}-report', 'html', html)
    return Report.objects.create(
        incident=None, type=ReportType.PERIODIC, format=ReportFormat.HTML,
        file_path=file_path, period_start=period_start, period_end=period_end,
    )


def generate_pdf_periodic_report(period_start, period_end):
    html = render_periodic_report_html(period_start, period_end)
    buffer = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buffer, encoding='utf-8')
    file_path = _write_file(f'periodic-{period_start:%Y-%m}-report', 'pdf', buffer.getvalue(), mode='wb')
    return Report.objects.create(
        incident=None, type=ReportType.PERIODIC, format=ReportFormat.PDF,
        file_path=file_path, period_start=period_start, period_end=period_end,
    )


def generate_csv_periodic_report(period_start, period_end):
    context = build_periodic_report_context(period_start, period_end)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['metric', 'value'])
    for metric, value in context['stats'].items():
        writer.writerow([metric, value])
    writer.writerow([])
    writer.writerow(['incident_id', 'type', 'start', 'end', 'severity', 'duration_seconds'])
    for incident in context['incidents']:
        writer.writerow([
            incident.id, incident.type, incident.start_time.isoformat(),
            incident.end_time.isoformat() if incident.end_time else '', incident.severity,
            incident.duration_seconds,
        ])
    file_path = _write_file(f'periodic-{period_start:%Y-%m}-report', 'csv', buffer.getvalue())
    return Report.objects.create(
        incident=None, type=ReportType.PERIODIC, format=ReportFormat.CSV,
        file_path=file_path, period_start=period_start, period_end=period_end,
    )


def generate_json_periodic_report(period_start, period_end):
    context = build_periodic_report_context(period_start, period_end)
    payload = {
        'period_start': period_start.isoformat(),
        'period_end': period_end.isoformat(),
        'stats': context['stats'],
        'incidents': [
            {
                'id': i.id, 'type': i.type, 'start_time': i.start_time.isoformat(),
                'end_time': i.end_time.isoformat() if i.end_time else None,
                'severity': i.severity, 'duration_seconds': i.duration_seconds,
            }
            for i in context['incidents']
        ],
        'sla_evaluations': [
            {
                'rule': e.rule.name, 'status': e.status, 'observed_value': e.observed_value,
                'threshold_value': e.threshold_value,
            }
            for e in context['sla_evaluations']
        ],
        'generated_at': context['generated_at'].isoformat(),
    }
    file_path = _write_file(f'periodic-{period_start:%Y-%m}-report', 'json', json.dumps(payload, indent=2))
    return Report.objects.create(
        incident=None, type=ReportType.PERIODIC, format=ReportFormat.JSON,
        file_path=file_path, period_start=period_start, period_end=period_end,
    )


def generate_periodic_reports(period_start, period_end):
    """Generates all 4 formats of a whole-period (e.g. monthly) summary report."""
    return [
        generate_html_periodic_report(period_start, period_end),
        generate_pdf_periodic_report(period_start, period_end),
        generate_csv_periodic_report(period_start, period_end),
        generate_json_periodic_report(period_start, period_end),
    ]


def generate_monthly_report(reference_date=None):
    """Generates a periodic report covering the calendar month containing `reference_date`
    (defaults to now) — intended to run at month-end (see apps/worker/jobs.py).
    """
    period_start, period_end = month_bounds(reference_date or timezone.now())
    return generate_periodic_reports(period_start, period_end)
