from django.db import models

from apps.core.models import AddressFamily, Target


class ICMPMeasurement(models.Model):
    """One ICMP probe result (a batch of echo requests) against a single Target."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='icmp_measurements')
    timestamp = models.DateTimeField()
    address_family = models.CharField(max_length=4, choices=AddressFamily.choices)
    sent = models.PositiveIntegerField()
    received = models.PositiveIntegerField()
    loss_pct = models.FloatField()
    min_rtt_ms = models.FloatField(null=True, blank=True)
    avg_rtt_ms = models.FloatField(null=True, blank=True)
    median_rtt_ms = models.FloatField(null=True, blank=True)
    max_rtt_ms = models.FloatField(null=True, blank=True)
    p95_rtt_ms = models.FloatField(null=True, blank=True)
    p99_rtt_ms = models.FloatField(null=True, blank=True)
    jitter_ms = models.FloatField(null=True, blank=True)
    # Populated when the probe itself failed (e.g. no ICMP permission) rather than merely lost packets.
    error = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['target', 'timestamp'])]

    def __str__(self):
        return f'{self.target.name} @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({self.loss_pct:.0f}% loss)'


class DNSResultType(models.TextChoices):
    SUCCESS = 'success', 'Success'
    TIMEOUT = 'timeout', 'Timeout'
    SERVFAIL = 'servfail', 'SERVFAIL'
    NXDOMAIN = 'nxdomain', 'NXDOMAIN'
    ERROR = 'error', 'Other error'


class DNSMeasurement(models.Model):
    """One DNS resolution attempt against a configured resolver Target."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='dns_measurements')
    timestamp = models.DateTimeField()
    resolver = models.CharField(max_length=255, help_text='Resolver address used, e.g. 1.1.1.1')
    query_name = models.CharField(max_length=255)
    query_type = models.CharField(max_length=10, default='A')
    resolution_time_ms = models.FloatField(null=True, blank=True)
    result_type = models.CharField(max_length=10, choices=DNSResultType.choices)
    resolved_ip = models.CharField(max_length=255, blank=True, default='')
    address_family = models.CharField(max_length=4, choices=AddressFamily.choices)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['target', 'timestamp'])]

    def __str__(self):
        return f'{self.query_name} via {self.resolver} @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({self.result_type})'


class HTTPMeasurement(models.Model):
    """One HTTP(S) request/response timing breakdown against a configured endpoint Target."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='http_measurements')
    timestamp = models.DateTimeField()
    dns_time_ms = models.FloatField(null=True, blank=True)
    connect_time_ms = models.FloatField(null=True, blank=True)
    tls_time_ms = models.FloatField(null=True, blank=True)
    ttfb_ms = models.FloatField(null=True, blank=True)
    total_time_ms = models.FloatField(null=True, blank=True)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    redirect_count = models.PositiveSmallIntegerField(default=0)
    address_family = models.CharField(max_length=4, choices=AddressFamily.choices)
    # Blank on success; set to e.g. 'timeout'/'connection_refused'/'tls_error' on failure.
    error_type = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['target', 'timestamp'])]

    def __str__(self):
        return f'{self.target.name} @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({self.status_code or self.error_type})'


class TCPMeasurement(models.Model):
    """One TCP connection attempt against a configured host:port Target."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='tcp_measurements')
    timestamp = models.DateTimeField()
    port = models.PositiveIntegerField()
    success = models.BooleanField()
    # Blank on success; e.g. 'timeout'/'refused'/'reset' on failure.
    error_type = models.CharField(max_length=50, blank=True, default='')
    connect_time_ms = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['target', 'timestamp'])]

    def __str__(self):
        return f'{self.target.name}:{self.port} @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({"ok" if self.success else self.error_type})'


class InterfaceMetric(models.Model):
    """A snapshot of local network interface counters (no remote target involved)."""

    timestamp = models.DateTimeField()
    interface_name = models.CharField(max_length=100)
    state = models.CharField(max_length=20)
    link_speed_mbps = models.IntegerField(null=True, blank=True)
    bytes_sent = models.BigIntegerField()
    bytes_received = models.BigIntegerField()
    packets_sent = models.BigIntegerField()
    packets_received = models.BigIntegerField()
    errors_in = models.PositiveIntegerField()
    errors_out = models.PositiveIntegerField()
    discards = models.PositiveIntegerField()

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['interface_name', 'timestamp'])]

    def __str__(self):
        return f'{self.interface_name} @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({self.state})'


class RouteTestRun(models.Model):
    """One traceroute run against a Target; hops are stored in related RouteHop rows."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='route_test_runs')
    timestamp = models.DateTimeField()
    address_family = models.CharField(max_length=4, choices=AddressFamily.choices)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['target', 'timestamp'])]

    def __str__(self):
        return f'Route to {self.target.name} @ {self.timestamp:%Y-%m-%d %H:%M:%S}'

    def route_hash(self):
        """Stable fingerprint of the hop sequence, used for route-change detection."""
        hops = self.hops.order_by('hop_number').values_list('ip_address', flat=True)
        return '>'.join(ip or '*' for ip in hops)


class RouteHop(models.Model):
    route_test_run = models.ForeignKey(RouteTestRun, on_delete=models.CASCADE, related_name='hops')
    hop_number = models.PositiveSmallIntegerField()
    ip_address = models.CharField(max_length=255, blank=True, default='')
    hostname = models.CharField(max_length=255, blank=True, default='')
    rtt_ms = models.FloatField(null=True, blank=True)
    timeout = models.BooleanField(default=False)

    class Meta:
        ordering = ['route_test_run', 'hop_number']
        unique_together = ('route_test_run', 'hop_number')

    def __str__(self):
        return f'hop {self.hop_number}: {self.ip_address or "*"}'


class RouteChangeEvent(models.Model):
    """Recorded when a RouteTestRun's hop sequence differs from the previous run for the same Target.

    An observed change here is not automatically a fault — see docs/STATE_MACHINE_AND_INCIDENTS.md.
    """

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='route_change_events')
    timestamp = models.DateTimeField()
    previous_route_hash = models.CharField(max_length=255, blank=True, default='')
    new_route_hash = models.CharField(max_length=255)
    hop_count_before = models.PositiveSmallIntegerField(null=True, blank=True)
    hop_count_after = models.PositiveSmallIntegerField()
    first_hop_changed = models.BooleanField()

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'Route change for {self.target.name} @ {self.timestamp:%Y-%m-%d %H:%M:%S}'


class MTUTestResult(models.Model):
    """Largest DF-set ping payload that succeeded, via a ping.exe -f -l sweep (see docs/DECISIONS.md)."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='mtu_test_results')
    timestamp = models.DateTimeField()
    largest_successful_size = models.PositiveIntegerField(help_text='Bytes, ICMP payload size')
    df_behavior = models.CharField(max_length=50, help_text='e.g. "honored", "fragmented", "unknown"')
    pmtud_response = models.CharField(max_length=100, blank=True, default='')
    failure_threshold = models.PositiveIntegerField(help_text='Smallest size that failed, bytes')

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['target', 'timestamp'])]

    def __str__(self):
        return f'MTU to {self.target.name} @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({self.largest_successful_size}B)'


class ThroughputTestType(models.TextChoices):
    DOWNLOAD = 'download', 'Download only'
    UPLOAD = 'upload', 'Upload only'
    BIDIRECTIONAL = 'bidirectional', 'Download + Upload'


class ThroughputMeasurement(models.Model):
    """One on-demand bandwidth test (§9/§10) — never run on a continuous schedule by default."""

    target = models.ForeignKey(
        Target, on_delete=models.CASCADE, related_name='throughput_measurements', null=True, blank=True
    )
    timestamp = models.DateTimeField()
    test_type = models.CharField(max_length=15, choices=ThroughputTestType.choices)
    mbps_down = models.FloatField(null=True, blank=True)
    mbps_up = models.FloatField(null=True, blank=True)
    avg_mbps = models.FloatField(null=True, blank=True)
    peak_mbps = models.FloatField(null=True, blank=True)
    min_mbps = models.FloatField(null=True, blank=True)
    variance = models.FloatField(null=True, blank=True)
    duration_s = models.FloatField(null=True, blank=True)
    endpoint = models.CharField(max_length=255, blank=True, default='')
    address_family = models.CharField(max_length=4, choices=AddressFamily.choices, default=AddressFamily.IPV4)
    test_size_bytes = models.BigIntegerField(null=True, blank=True)
    error = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.test_type} @ {self.timestamp:%Y-%m-%d %H:%M:%S}'


class BufferbloatTest(models.Model):
    """Idle vs. loaded latency comparison (§11) — a single measurement, not an automatic verdict.

    `classification` is a descriptive label (e.g. "none"/"moderate"/"severe") that a human or the
    incident engine can independently re-derive from the stored RTT/loss/throughput fields.
    """

    timestamp = models.DateTimeField()
    baseline_rtt_ms = models.FloatField()
    loaded_rtt_download_ms = models.FloatField(null=True, blank=True)
    loaded_rtt_upload_ms = models.FloatField(null=True, blank=True)
    loaded_rtt_bidirectional_ms = models.FloatField(null=True, blank=True)
    loss_during_load_pct = models.FloatField(null=True, blank=True)
    throughput_during_load_mbps = models.FloatField(null=True, blank=True)
    recovery_time_s = models.FloatField(null=True, blank=True)
    classification = models.CharField(max_length=20, blank=True, default='')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'Bufferbloat test @ {self.timestamp:%Y-%m-%d %H:%M:%S} ({self.classification or "unclassified"})'


class HourlyAggregate(models.Model):
    """One hour's rollup of a metric for a target (§31) — raw rows may later be pruned by retention,
    but this aggregate (and any Incident/SLAEvaluation) is preserved independently.
    """

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='hourly_aggregates', null=True, blank=True)
    metric = models.CharField(max_length=30)
    period_start = models.DateTimeField()
    avg_value = models.FloatField()
    min_value = models.FloatField()
    max_value = models.FloatField()
    p95_value = models.FloatField()
    sample_count = models.PositiveIntegerField()

    class Meta:
        ordering = ['-period_start']
        unique_together = ('target', 'metric', 'period_start')
        indexes = [models.Index(fields=['metric', 'period_start'])]

    def __str__(self):
        return f'{self.metric} hourly @ {self.period_start:%Y-%m-%d %H:00}'


class DailyAggregate(models.Model):
    """One day's rollup of an HourlyAggregate metric (§31)."""

    target = models.ForeignKey(Target, on_delete=models.CASCADE, related_name='daily_aggregates', null=True, blank=True)
    metric = models.CharField(max_length=30)
    period_start = models.DateField()
    avg_value = models.FloatField()
    min_value = models.FloatField()
    max_value = models.FloatField()
    p95_value = models.FloatField()
    sample_count = models.PositiveIntegerField()

    class Meta:
        ordering = ['-period_start']
        unique_together = ('target', 'metric', 'period_start')
        indexes = [models.Index(fields=['metric', 'period_start'])]

    def __str__(self):
        return f'{self.metric} daily @ {self.period_start:%Y-%m-%d}'

