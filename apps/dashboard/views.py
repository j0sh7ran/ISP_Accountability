from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.elevation import is_elevated
from apps.incidents.models import Incident
from apps.measurements.models import ICMPMeasurement
from apps.network_state.models import NetworkStateLog

from . import services


def _parse_custom_datetime(value):
    """?start=/&end= come from an HTML datetime-local input, so they're naive local times."""
    dt = parse_datetime(value) if value else None
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def overview(request):
    family = request.GET.get('family') or None
    context = {
        'state': services.current_state(),
        'icmp_rows': services.latest_icmp_by_target(address_family=family),
        'dns_rows': services.latest_dns_status(),
        'http_rows': services.latest_http_status(),
        'active_incidents': services.active_incidents(),
        'recent_incidents': services.recent_incidents(limit=5),
        'sla_violations': services.recent_sla_violations(limit=5),
        'uptime_pct': services.uptime_pct(hours=24),
        'family': family or 'all',
        'elevated': is_elevated(),
        'job_summary': services.job_status_summary(),
    }
    return render(request, 'dashboard/overview.html', context)


def api_overview(request):
    """Polled every few seconds by the overview page — see docs/ARCHITECTURE.md non-blocking design."""
    family = request.GET.get('family') or None
    icmp_rows = services.latest_icmp_by_target(address_family=family)
    job_summary = services.job_status_summary()
    return JsonResponse({
        'state': services.current_state(),
        'uptime_pct': services.uptime_pct(hours=24),
        'active_incident_count': len(services.active_incidents()),
        'sla_violation_count': len(services.recent_sla_violations(limit=50)),
        'generated_at': timezone.now().isoformat(),
        'jobs': job_summary['jobs'],
        'pending_on_demand': job_summary['pending_on_demand'],
        'targets': [
            {
                'name': row['target'].name,
                'address': row['target'].address,
                'loss_pct': row['measurement'].loss_pct if row['measurement'] else None,
                'avg_rtt_ms': row['measurement'].avg_rtt_ms if row['measurement'] else None,
                'timestamp': row['measurement'].timestamp.isoformat() if row['measurement'] else None,
            }
            for row in icmp_rows
        ],
    })


def graphs(request):
    range_key = request.GET.get('range', '24h')
    family = request.GET.get('family') or None
    context = {
        'range_key': range_key,
        'family': family or 'all',
        'range_choices': list(services.RANGE_CHOICES),
        'start_param': request.GET.get('start', ''),
        'end_param': request.GET.get('end', ''),
    }
    return render(request, 'dashboard/graphs.html', context)


def api_timeseries(request):
    metric = request.GET.get('metric', 'latency_ms')
    range_key = request.GET.get('range', '24h')
    family = request.GET.get('family') or None
    custom_start = _parse_custom_datetime(request.GET.get('start', ''))
    custom_end = _parse_custom_datetime(request.GET.get('end', ''))
    window_start, window_end = services.resolve_range(range_key, custom_start=custom_start, custom_end=custom_end)
    points = services.timeseries(metric, window_start, window_end, address_family=family)
    return JsonResponse({
        'metric': metric, 'points': points,
        'window_start': window_start.isoformat(), 'window_end': window_end.isoformat(),
    })


def incidents_list(request):
    return render(request, 'dashboard/incidents_list.html', {'incidents': Incident.objects.order_by('-start_time')})



def incident_detail(request, incident_id):
    incident = get_object_or_404(Incident, pk=incident_id)
    window_start = incident.start_time - timezone.timedelta(minutes=10)
    window_end = (incident.end_time or timezone.now()) + timezone.timedelta(minutes=10)
    nearby_icmp = ICMPMeasurement.objects.filter(
        timestamp__gte=window_start, timestamp__lte=window_end
    ).order_by('timestamp')
    context = {
        'incident': incident,
        'events': incident.events.order_by('start_time'),
        'sla_evaluations': incident.sla_evaluations.order_by('-window_end'),
        'nearby_icmp': nearby_icmp,
        'state_logs': NetworkStateLog.objects.filter(
            timestamp__gte=window_start, timestamp__lte=window_end
        ).order_by('timestamp'),
    }
    return render(request, 'dashboard/incident_detail.html', context)


def sla_comparison(request):
    """SLA comparison view (§30) — kept visually/semantically separate from baseline comparison."""
    return render(request, 'dashboard/sla_comparison.html', {'rows': services.sla_comparison_rows()})


def baseline_comparison(request):
    """Industry baseline comparison view (§29) — descriptive only, never pass/fail."""
    hours = int(request.GET.get('hours', 24))
    return render(request, 'dashboard/baseline_comparison.html', {
        'rows': services.baseline_comparison_rows(hours=hours), 'hours': hours,
    })


def historical_comparison(request):
    """Current-period vs. previous-period comparison (§28) — underlying data shown, no single score."""
    hours = int(request.GET.get('hours', 24))
    return render(request, 'dashboard/historical_comparison.html', {
        **services.historical_comparison(hours=hours),
    })

