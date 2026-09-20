from django.db import migrations

# Placeholder example data so the comparison feature is exercisable out of the box. This is NOT a
# verified industry figure — replace/extend via the admin with properly sourced baselines before
# relying on this for any real comparison (see docs/SLA_AND_BASELINES.md and docs/DECISIONS.md).
PLACEHOLDER_BASELINES = [
    {
        'metric': 'latency_ms',
        'value': 25.0,
        'unit': 'ms',
        'population_context': 'Example placeholder only',
        'technology_type': '',
        'geographic_scope': '',
        'source': 'Example placeholder — not a verified source',
        'source_url': '',
        'methodology': '',
        'notes': 'Seeded as a placeholder so the baseline-comparison feature has something to show. '
                 'Replace with a real, cited industry baseline before drawing any conclusions from it.',
        'version': 1,
    },
]


def seed_placeholder(apps, schema_editor):
    Baseline = apps.get_model('baselines', 'Baseline')
    for entry in PLACEHOLDER_BASELINES:
        Baseline.objects.get_or_create(
            metric=entry['metric'], version=entry['version'],
            technology_type=entry['technology_type'], geographic_scope=entry['geographic_scope'],
            defaults=entry,
        )


def remove_placeholder(apps, schema_editor):
    Baseline = apps.get_model('baselines', 'Baseline')
    for entry in PLACEHOLDER_BASELINES:
        Baseline.objects.filter(metric=entry['metric'], version=entry['version'], source=entry['source']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('baselines', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_placeholder, remove_placeholder),
    ]
