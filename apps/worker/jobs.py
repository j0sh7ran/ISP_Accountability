"""Hosts jobs run by the worker's scheduler (see apps/worker/management/commands/run_worker.py).

Kept out of the management command module so jobs can be unit tested without going through
APScheduler/CLI plumbing.
"""
import logging
import threading

from django.utils import timezone

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
    RouteHop,
    RouteTestRun,
    TCPMeasurement,
    ThroughputMeasurement,
    ThroughputTestType,
)
from apps.measurements.probes.bufferbloat import run_bufferbloat_probe
from apps.measurements.probes.dns import run_dns_probe
from apps.measurements.probes.http import run_http_probe
from apps.measurements.probes.icmp import run_icmp_probe
from apps.measurements.probes.interface import collect_interface_metrics
from apps.measurements.probes.mtu import run_mtu_probe
from apps.measurements.probes.route import run_traceroute
from apps.measurements.probes.tcp import run_tcp_probe
from apps.measurements.probes.throughput import run_throughput_probe
from apps.network_state.evaluator import evaluate_and_log_state
from apps.incidents.derivation import derive_bufferbloat_events, derive_route_change_events
from apps.sla.engine import evaluate_periodic_rules
from apps.measurements.aggregation import run_aggregation
from apps.measurements.retention import enforce_retention

logger = logging.getLogger(__name__)

# Query name used for DNS resolver probes. Not yet user-configurable — see docs/DECISIONS.md.
DEFAULT_DNS_QUERY_NAME = 'www.example.com'

# Route/MTU probes only make sense against representative upstream targets, not every DNS/HTTP target.
ROUTE_TARGET_CATEGORIES = [TargetCategory.GATEWAY, TargetCategory.ISP_HOP, TargetCategory.INTERNET]

# Throughput and bufferbloat share one lock so they never run simultaneously (§9/§11).
BANDWIDTH_TEST_LOCK = threading.Lock()

# Task types that are on-demand by default: their job always runs on a short poll interval to check
# for a pending OnDemandTestRequest, even when their ScheduleConfig is disabled (see run_worker.py).
ON_DEMAND_TASK_TYPES = {MeasurementCategory.THROUGHPUT, MeasurementCategory.BUFFERBLOAT}


def run_icmp_job():
    """Probe every enabled ICMP target once and record the results."""
    targets = Target.objects.filter(enabled=True, protocol=Protocol.ICMP)
    for target in targets:
        result = run_icmp_probe(target.address)
        ICMPMeasurement.objects.create(
            target=target,
            timestamp=timezone.now(),
            address_family=target.address_family,
            **result,
        )
        if result['error']:
            logger.warning('ICMP probe failed for %s: %s', target.name, result['error'])

    evaluate_and_log_state()
    ScheduleConfig.objects.filter(task_type=MeasurementCategory.ICMP).update(last_run=timezone.now())


def run_dns_job():
    targets = Target.objects.filter(enabled=True, category=TargetCategory.DNS)
    for target in targets:
        result = run_dns_probe(target.address, DEFAULT_DNS_QUERY_NAME)
        DNSMeasurement.objects.create(
            target=target,
            timestamp=timezone.now(),
            resolver=target.address,
            query_name=DEFAULT_DNS_QUERY_NAME,
            query_type='A',
            address_family=target.address_family,
            **result,
        )

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.DNS).update(last_run=timezone.now())


def run_http_job():
    targets = Target.objects.filter(enabled=True, category=TargetCategory.HTTP)
    for target in targets:
        result = run_http_probe(target.address)
        HTTPMeasurement.objects.create(
            target=target, timestamp=timezone.now(), address_family=target.address_family, **result,
        )

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.HTTP).update(last_run=timezone.now())


def run_tcp_job():
    targets = Target.objects.filter(enabled=True, protocol=Protocol.TCP)
    for target in targets:
        if not target.port:
            logger.warning('Skipping TCP probe for %s: no port configured', target.name)
            continue
        result = run_tcp_probe(target.address, target.port)
        TCPMeasurement.objects.create(
            target=target, timestamp=timezone.now(), port=target.port, **result,
        )

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.TCP).update(last_run=timezone.now())


def run_interface_job():
    for metric in collect_interface_metrics():
        InterfaceMetric.objects.create(timestamp=timezone.now(), **metric)

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.INTERFACE).update(last_run=timezone.now())


def run_route_job():
    targets = Target.objects.filter(enabled=True, category__in=ROUTE_TARGET_CATEGORIES)
    for target in targets:
        hops = run_traceroute(target.address)
        if not hops:
            continue

        previous_run = RouteTestRun.objects.filter(target=target).order_by('-timestamp').first()
        previous_hash = previous_run.route_hash() if previous_run else None
        previous_hop_count = previous_run.hops.count() if previous_run else None
        previous_first_ip = (
            previous_run.hops.order_by('hop_number').values_list('ip_address', flat=True).first()
            if previous_run else None
        )

        run = RouteTestRun.objects.create(
            target=target, timestamp=timezone.now(), address_family=target.address_family,
        )
        RouteHop.objects.bulk_create([
            RouteHop(
                route_test_run=run, hop_number=h['hop_number'], ip_address=h['ip_address'],
                hostname=h['hostname'], rtt_ms=h['rtt_ms'], timeout=h['timeout'],
            )
            for h in hops
        ])

        new_hash = run.route_hash()
        if previous_hash is not None and previous_hash != new_hash:
            new_first_ip = run.hops.order_by('hop_number').values_list('ip_address', flat=True).first()
            RouteChangeEvent.objects.create(
                target=target,
                timestamp=timezone.now(),
                previous_route_hash=previous_hash,
                new_route_hash=new_hash,
                hop_count_before=previous_hop_count,
                hop_count_after=run.hops.count(),
                first_hop_changed=(previous_first_ip != new_first_ip),
            )

    derive_route_change_events()
    ScheduleConfig.objects.filter(task_type=MeasurementCategory.ROUTE).update(last_run=timezone.now())


def run_mtu_job():
    targets = Target.objects.filter(enabled=True, category__in=ROUTE_TARGET_CATEGORIES)
    for target in targets:
        result = run_mtu_probe(target.address)
        MTUTestResult.objects.create(target=target, timestamp=timezone.now(), **result)

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.MTU).update(last_run=timezone.now())


def _should_run_bandwidth_test(task_type):
    """An on-demand task runs if there's a pending request, or the user explicitly enabled its
    ScheduleConfig for periodic runs (still off by default per §9)."""
    request = (
        OnDemandTestRequest.objects.filter(task_type=task_type, status=OnDemandTestStatus.PENDING)
        .order_by('requested_at').first()
    )
    schedule = ScheduleConfig.objects.filter(task_type=task_type).first()
    scheduled_enabled = bool(schedule and schedule.enabled)
    return request, scheduled_enabled


def run_throughput_job():
    request, scheduled_enabled = _should_run_bandwidth_test(MeasurementCategory.THROUGHPUT)
    if request is None and not scheduled_enabled:
        return
    if not BANDWIDTH_TEST_LOCK.acquire(blocking=False):
        logger.info('Skipping throughput test — another bandwidth-intensive test is already running')
        return
    try:
        if request:
            request.status = OnDemandTestStatus.RUNNING
            request.started_at = timezone.now()
            request.save(update_fields=['status', 'started_at'])

        result = run_throughput_probe('bidirectional')
        ThroughputMeasurement.objects.create(
            timestamp=timezone.now(),
            test_type=ThroughputTestType.BIDIRECTIONAL,
            mbps_down=result['mbps_down'],
            mbps_up=result['mbps_up'],
            duration_s=result['duration_s'],
            endpoint=result['endpoint'],
            error=result['error'],
        )

        if request:
            request.status = OnDemandTestStatus.FAILED if result['error'] else OnDemandTestStatus.COMPLETED
            request.completed_at = timezone.now()
            request.save(update_fields=['status', 'completed_at'])
    finally:
        BANDWIDTH_TEST_LOCK.release()

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.THROUGHPUT).update(last_run=timezone.now())


def run_bufferbloat_job():
    request, scheduled_enabled = _should_run_bandwidth_test(MeasurementCategory.BUFFERBLOAT)
    if request is None and not scheduled_enabled:
        return

    gateway = Target.objects.filter(enabled=True, category=TargetCategory.GATEWAY).first()
    if gateway is None:
        logger.warning('Skipping bufferbloat test: no enabled gateway Target configured')
        if request:
            # Otherwise the request sits at "pending" forever with no feedback that it can't run.
            request.status = OnDemandTestStatus.FAILED
            request.completed_at = timezone.now()
            request.save(update_fields=['status', 'completed_at'])
        return

    if not BANDWIDTH_TEST_LOCK.acquire(blocking=False):
        logger.info('Skipping bufferbloat test — another bandwidth-intensive test is already running')
        return
    try:
        if request:
            request.status = OnDemandTestStatus.RUNNING
            request.started_at = timezone.now()
            request.save(update_fields=['status', 'started_at'])

        result = run_bufferbloat_probe(gateway.address)
        BufferbloatTest.objects.create(timestamp=timezone.now(), **result)
        derive_bufferbloat_events()

        if request:
            request.status = OnDemandTestStatus.COMPLETED
            request.completed_at = timezone.now()
            request.save(update_fields=['status', 'completed_at'])
    finally:
        BANDWIDTH_TEST_LOCK.release()

    ScheduleConfig.objects.filter(task_type=MeasurementCategory.BUFFERBLOAT).update(last_run=timezone.now())


def run_sla_periodic_job():
    """Evaluates window-based SLA rules (e.g. monthly availability) independent of any one incident."""
    evaluate_periodic_rules()


def run_aggregation_job():
    """Rolls up the most recently completed hour (and day, once complete) of raw measurements."""
    run_aggregation()


def run_retention_job():
    """Enforces each RetentionPolicy's configured raw/aggregate age limits (default: indefinite)."""
    enforce_retention()


def run_monthly_report_job():
    """Generates the current month's periodic report — scheduled for month-end (see run_worker.py's
    CronTrigger(day='last')); safe to call any time, always summarizes the month `timezone.now()` falls in.
    """
    from apps.reports.generators import generate_monthly_report

    generate_monthly_report()


# Maps MeasurementCategory -> job callable, consumed by run_worker.py to register APScheduler jobs.
JOBS = {
    MeasurementCategory.ICMP: run_icmp_job,
    MeasurementCategory.DNS: run_dns_job,
    MeasurementCategory.HTTP: run_http_job,
    MeasurementCategory.TCP: run_tcp_job,
    MeasurementCategory.INTERFACE: run_interface_job,
    MeasurementCategory.ROUTE: run_route_job,
    MeasurementCategory.MTU: run_mtu_job,
    MeasurementCategory.THROUGHPUT: run_throughput_job,
    MeasurementCategory.BUFFERBLOAT: run_bufferbloat_job,
}
