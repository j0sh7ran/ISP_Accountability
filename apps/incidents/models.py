from django.db import models


class EventType(models.TextChoices):
    OUTAGE = 'outage', 'Outage'
    MICRO_OUTAGE = 'micro_outage', 'Micro-outage'
    PACKET_LOSS = 'packet_loss', 'Packet loss'
    LATENCY_DEGRADATION = 'latency_degradation', 'Latency degradation'
    JITTER_DEGRADATION = 'jitter_degradation', 'Jitter degradation'
    THROUGHPUT_DEGRADATION = 'throughput_degradation', 'Throughput degradation'
    DNS_FAILURE = 'dns_failure', 'DNS failure'
    DNS_DEGRADATION = 'dns_degradation', 'DNS degradation'
    ROUTE_CHANGE = 'route_change', 'Route change'
    IPV6_FAILURE = 'ipv6_failure', 'IPv6 failure'
    MTU_FAILURE = 'mtu_failure', 'MTU failure'
    BUFFERBLOAT = 'bufferbloat', 'Bufferbloat'
    CONNECTION_FAILURE = 'connection_failure', 'Connection failure'


class Severity(models.TextChoices):
    INFO = 'info', 'Info'
    WARNING = 'warning', 'Warning'
    CRITICAL = 'critical', 'Critical'


class RecoveryStatus(models.TextChoices):
    ONGOING = 'ongoing', 'Ongoing'
    RECOVERED = 'recovered', 'Recovered'
    UNKNOWN = 'unknown', 'Unknown'


class Incident(models.Model):
    """A group of related Events (§20/§21).

    `report` (FK to apps.reports.Report) is added in Phase 7 once that model exists.
    """

    type = models.CharField(max_length=30, choices=EventType.choices)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    affected_tests = models.JSONField(default=list, blank=True)
    affected_destinations = models.JSONField(default=list, blank=True)
    recovery_status = models.CharField(max_length=10, choices=RecoveryStatus.choices, default=RecoveryStatus.ONGOING)

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f'{self.get_type_display()} @ {self.start_time:%Y-%m-%d %H:%M:%S} ({self.recovery_status})'


class Event(models.Model):
    """A typed, evidenced observation (§20/§21) — description uses qualifying language, not an
    asserted root cause (e.g. "Observed"/"Consistent with"), per docs/STATE_MACHINE_AND_INCIDENTS.md.
    """

    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name='events', null=True, blank=True
    )
    type = models.CharField(max_length=30, choices=EventType.choices)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    description = models.TextField()

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f'{self.get_type_display()} @ {self.start_time:%Y-%m-%d %H:%M:%S}'


class EventEvidence(models.Model):
    """Points at a specific measurement row backing an Event (§21).

    Not a real FK — the measurement lives in one of many different tables; see the
    "Notes" section of docs/DATA_MODEL.md for why this is deliberate.
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='evidence')
    measurement_type = models.CharField(max_length=30, help_text='Measurement model name, e.g. "ICMPMeasurement"')
    measurement_id = models.PositiveIntegerField()

    class Meta:
        indexes = [models.Index(fields=['measurement_type', 'measurement_id'])]

    def __str__(self):
        return f'{self.measurement_type}#{self.measurement_id} for event #{self.event_id}'
