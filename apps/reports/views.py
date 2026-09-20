from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import exports
from .models import Report

CONTENT_TYPES = {
    'html': 'text/html',
    'pdf': 'application/pdf',
    'csv': 'text/csv',
    'json': 'application/json',
}


def reports_list(request):
    """All generated reports (per-incident outage reports + periodic/monthly summaries)."""
    return render(request, 'reports/reports_list.html', {'reports': Report.objects.select_related('incident')})


def download_report(request, report_id):
    report = get_object_or_404(Report, pk=report_id)
    if not report.file_path:
        raise Http404('Report has no generated file')
    path = Path(settings.MEDIA_ROOT) / 'reports' / Path(report.file_path).name
    if not path.exists():
        raise Http404('Report file is missing on disk')
    return FileResponse(
        open(path, 'rb'), content_type=CONTENT_TYPES.get(report.format, 'application/octet-stream'),
        filename=path.name,
    )


def _parse_window(request, default_days=30):
    """?start=&end= as ISO datetimes; defaults to the last `default_days` days."""
    now = timezone.now()
    start = parse_datetime(request.GET.get('start', '')) or (now - timedelta(days=default_days))
    end = parse_datetime(request.GET.get('end', '')) or now
    return start, end


def export_measurements_view(request, data_type):
    window_start, window_end = _parse_window(request)
    response = exports.export_measurements(data_type, window_start, window_end, fmt=request.GET.get('format', 'csv'))
    if response is None:
        raise Http404(f'Unknown measurement type: {data_type}')
    return response


def export_incidents_view(request):
    window_start, window_end = _parse_window(request)
    return exports.export_incidents(window_start, window_end, fmt=request.GET.get('format', 'csv'))
