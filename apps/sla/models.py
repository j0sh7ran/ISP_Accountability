from django.db import models

from apps.incidents.models import Incident, Severity


class SLAMetric(models.TextChoices):
    """The set of metrics the evaluation engine (engine.py) knows how to compute (see docs/SLA_AND_BASELINES.md)."""

    PACKET_LOSS_PCT = 'packet_loss_pct', 'Packet loss (%)'
    LATENCY_MS = 'latency_ms', 'Latency (ms)'
    JITTER_MS = 'jitter_ms', 'Jitter (ms)'
    AVAILABILITY_PCT = 'availability_pct', 'Availability (%)'
    OUTAGE_DURATION_S = 'outage_duration_s', 'Outage duration (s)'
    THROUGHPUT_MBPS = 'throughput_mbps', 'Throughput (Mbps)'
    DNS_RESOLUTION_MS = 'dns_resolution_ms', 'DNS resolution time (ms)'


class SLAOperator(models.TextChoices):
    GT = 'gt', '>'
    GTE = 'gte', '>='
    LT = 'lt', '<'
    LTE = 'lte', '<='
    EQ = 'eq', '=='


class SLAEvaluationStatus(models.TextChoices):
    SATISFIED = 'satisfied', 'Satisfied'
    BREACHED = 'breached', 'Breached'
    INSUFFICIENT_DATA = 'insufficient_data', 'Insufficient data'


class SLARule(models.Model):
    """A user-entered ISP contract term — never a hard-coded "real" SLA value (§22).

    The application ships with zero rules; the user must enter their own contract terms.
    """

    name = models.CharField(max_length=255)
    metric = models.CharField(max_length=30, choices=SLAMetric.choices)
    operator = models.CharField(max_length=5, choices=SLAOperator.choices)
    threshold = models.FloatField()
    unit = models.CharField(max_length=20, blank=True, default='')
    min_duration_seconds = models.PositiveIntegerField(
        default=0, help_text='The breach must have lasted at least this long to count (0 = any duration)'
    )
    measurement_window_seconds = models.PositiveIntegerField(
        help_text='Rolling window size for periodic evaluation, e.g. 2592000 for a 30-day window'
    )
    protocol = models.CharField(max_length=10, blank=True, default='')
    destination_filter = models.CharField(
        max_length=255, blank=True, default='', help_text='Target name/address substring; blank = all targets'
    )
    time_period_filter = models.CharField(
        max_length=100, blank=True, default='', help_text='e.g. "business_hours"; blank = all times'
    )
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.get_metric_display()} {self.get_operator_display()} {self.threshold}{self.unit})'


class SLAEvaluation(models.Model):
    """One evaluation of an SLARule over a specific window — see docs/SLA_AND_BASELINES.md."""

    rule = models.ForeignKey(SLARule, on_delete=models.CASCADE, related_name='evaluations')
    incident = models.ForeignKey(
        Incident, on_delete=models.CASCADE, related_name='sla_evaluations', null=True, blank=True
    )
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    observed_value = models.FloatField(null=True, blank=True)
    threshold_value = models.FloatField()
    status = models.CharField(max_length=20, choices=SLAEvaluationStatus.choices)
    evidence = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-window_end']

    def __str__(self):
        return f'{self.rule.name}: {self.status} ({self.window_start:%Y-%m-%d} - {self.window_end:%Y-%m-%d})'
