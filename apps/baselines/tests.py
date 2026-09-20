from django.test import TestCase

from .comparison import compare_metric
from .models import Baseline


class CompareMetricTests(TestCase):
    def test_returns_none_when_no_baseline_configured(self):
        result = compare_metric('nonexistent_metric', 42.0)

        self.assertIsNone(result)

    def test_computes_difference_and_percentage(self):
        Baseline.objects.create(metric='jitter_ms', value=25.0, source='Test source', version=1)

        result = compare_metric('jitter_ms', 20.0)

        self.assertEqual(result['difference'], -5.0)
        self.assertAlmostEqual(result['pct_difference'], -20.0)

    def test_uses_latest_version_when_multiple_exist(self):
        Baseline.objects.create(metric='jitter_ms', value=30.0, source='Old', version=1)
        Baseline.objects.create(metric='jitter_ms', value=20.0, source='New', version=2)

        result = compare_metric('jitter_ms', 20.0)

        self.assertEqual(result['baseline'].source, 'New')
        self.assertEqual(result['difference'], 0.0)


    def test_placeholder_seed_data_is_present(self):
        result = compare_metric('latency_ms', 21.0)

        self.assertIsNotNone(result)
        self.assertEqual(result['baseline'].source, 'Example placeholder — not a verified source')
