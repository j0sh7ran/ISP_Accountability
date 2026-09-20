from django.db import models


class Baseline(models.Model):
    """A versioned industry reference value — descriptive only, never a contractual requirement (§23).

    Deliberately has no FK to any measurement table; comparisons match on `metric` at query time
    (see docs/SLA_AND_BASELINES.md) so this stays fully decoupled from SLA/contract data.
    """

    metric = models.CharField(max_length=30, help_text='Matches an SLAMetric key, e.g. "latency_ms"')
    value = models.FloatField()
    unit = models.CharField(max_length=20, blank=True, default='')
    population_context = models.CharField(max_length=255, blank=True, default='')
    technology_type = models.CharField(max_length=100, blank=True, default='', help_text='e.g. "cable", "fiber", "DSL"')
    geographic_scope = models.CharField(max_length=100, blank=True, default='')
    source = models.CharField(max_length=255)
    source_url = models.URLField(blank=True, default='')
    publication_date = models.DateField(null=True, blank=True)
    methodology = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['metric', '-version']
        unique_together = ('metric', 'version', 'technology_type', 'geographic_scope')

    def __str__(self):
        return f'{self.metric} = {self.value}{self.unit} (v{self.version}, {self.source})'
