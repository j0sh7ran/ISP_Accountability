"""Baseline comparison (§29) — descriptive only, never pass/fail; see docs/SLA_AND_BASELINES.md."""
from .models import Baseline


def compare_metric(metric, observed_value, technology_type='', geographic_scope=''):
    """Compare `observed_value` against the latest-version Baseline for `metric` (optionally scoped).

    Returns None if no baseline is configured for this metric — never fabricates a comparison.
    """
    qs = Baseline.objects.filter(metric=metric)
    if technology_type:
        qs = qs.filter(technology_type=technology_type)
    if geographic_scope:
        qs = qs.filter(geographic_scope=geographic_scope)

    baseline = qs.order_by('-version').first()
    if baseline is None:
        return None

    difference = observed_value - baseline.value
    pct_difference = (difference / baseline.value * 100) if baseline.value else None
    return {
        'baseline': baseline,
        'observed_value': observed_value,
        'difference': difference,
        'pct_difference': pct_difference,
    }
