from django.db import models


class AddressFamily(models.TextChoices):
    IPV4 = 'ipv4', 'IPv4'
    IPV6 = 'ipv6', 'IPv6'


class TargetCategory(models.TextChoices):
    GATEWAY = 'gateway', 'Default gateway'
    ISP_HOP = 'isp_hop', 'ISP first hop'
    INTERNET = 'internet', 'Internet endpoint'
    DNS = 'dns', 'DNS resolver'
    HTTP = 'http', 'HTTP(S) endpoint'
    CUSTOM = 'custom', 'Custom'


class Protocol(models.TextChoices):
    ICMP = 'icmp', 'ICMP'
    TCP = 'tcp', 'TCP'
    UDP = 'udp', 'UDP'
    HTTP = 'http', 'HTTP'
    HTTPS = 'https', 'HTTPS'
    DNS = 'dns', 'DNS'


class Target(models.Model):
    """A configured probe destination (gateway, ISP hop, DNS resolver, HTTP endpoint, etc.)."""

    name = models.CharField(max_length=255, unique=True)
    category = models.CharField(max_length=20, choices=TargetCategory.choices)
    address = models.CharField(max_length=255, help_text='Hostname, IP address, or URL (for HTTP targets)')
    address_family = models.CharField(
        max_length=4, choices=AddressFamily.choices, default=AddressFamily.IPV4
    )
    protocol = models.CharField(max_length=10, choices=Protocol.choices)
    port = models.PositiveIntegerField(null=True, blank=True, help_text='Required for TCP targets')
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.name} ({self.address})'


class MeasurementCategory(models.TextChoices):
    """Shared across ScheduleConfig (how often) and RetentionPolicy (how long kept)."""

    ICMP = 'icmp', 'ICMP latency/loss'
    DNS = 'dns', 'DNS resolution'
    HTTP = 'http', 'HTTP/HTTPS'
    TCP = 'tcp', 'TCP connect'
    ROUTE = 'route', 'Route trace'
    MTU = 'mtu', 'MTU/PMTUD'
    THROUGHPUT = 'throughput', 'Throughput'
    BUFFERBLOAT = 'bufferbloat', 'Bufferbloat'
    INTERFACE = 'interface', 'Interface metrics'


class ScheduleConfig(models.Model):
    """Run interval per probe category; read by the worker instead of hard-coded (see §17)."""

    task_type = models.CharField(max_length=20, choices=MeasurementCategory.choices, unique=True)
    interval_seconds = models.PositiveIntegerField()
    enabled = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['task_type']

    def __str__(self):
        return f'{self.get_task_type_display()} every {self.interval_seconds}s'


class RetentionPolicy(models.Model):
    """Raw/aggregate retention per data type (see §31).

    Incidents and SLA evaluations are always exempt from deletion regardless of policy — that
    exemption is enforced by the retention job (Phase 8), not by this model.
    """

    data_type = models.CharField(max_length=20, choices=MeasurementCategory.choices, unique=True)
    raw_retention_days = models.PositiveIntegerField(
        null=True, blank=True, help_text='Blank = keep raw data indefinitely'
    )
    aggregate_retention_days = models.PositiveIntegerField(
        null=True, blank=True, help_text='Blank = keep aggregates indefinitely'
    )

    class Meta:
        ordering = ['data_type']

    def __str__(self):
        return self.get_data_type_display()


class OnDemandTestStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class OnDemandTestRequest(models.Model):
    """A manual trigger for a bandwidth-intensive test (throughput/bufferbloat), written by the web
    process and picked up by the worker on its next scheduling tick (see docs/WORKER_AND_SCHEDULING.md).
    Only ``throughput``/``bufferbloat`` task types are meaningful here.
    """

    task_type = models.CharField(max_length=20, choices=MeasurementCategory.choices)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=OnDemandTestStatus.choices, default=OnDemandTestStatus.PENDING)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.get_task_type_display()} requested {self.requested_at:%Y-%m-%d %H:%M:%S} ({self.status})'
