from django.db import models

from apps.incidents.models import Incident


class ReportType(models.TextChoices):
    OUTAGE = 'outage', 'Outage'
    PERIODIC = 'periodic', 'Periodic'
    CUSTOM = 'custom', 'Custom'


class ReportFormat(models.TextChoices):
    HTML = 'html', 'HTML'
    PDF = 'pdf', 'PDF'
    CSV = 'csv', 'CSV'
    JSON = 'json', 'JSON'


class Report(models.Model):
    """A generated report document (§26/§27) — metadata only; the rendered content lives on disk
    under MEDIA_ROOT/reports/ (see docs/REPORTING_AND_RETENTION.md), not in this table.

    One incident can have several Report rows (one per format) — a one-to-many relationship rather
    than the single `Incident.report` FK originally sketched in docs/DATA_MODEL.md; see
    docs/DECISIONS.md for why.
    """

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='reports', null=True, blank=True)
    type = models.CharField(max_length=20, choices=ReportType.choices)
    format = models.CharField(max_length=10, choices=ReportFormat.choices)
    generated_at = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(max_length=500, blank=True, default='')
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    class Meta:
        ordering = ['-generated_at']

    def __str__(self):
        return f'{self.get_type_display()} report ({self.format}) generated {self.generated_at:%Y-%m-%d %H:%M:%S}'
