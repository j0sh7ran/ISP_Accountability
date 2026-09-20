from django.db import migrations

# Suggested defaults from docs/WORKER_AND_SCHEDULING.md; user-editable afterwards via admin.
SCHEDULE_DEFAULTS = [
    # (task_type, interval_seconds, enabled)
    ('icmp', 30, True),
    ('dns', 300, True),
    ('http', 300, True),
    ('tcp', 300, True),
    ('route', 300, True),
    ('mtu', 21600, True),
    ('interface', 60, True),
    # Bandwidth-intensive tests default to disabled/manual-trigger only (§9).
    ('throughput', 86400, False),
    ('bufferbloat', 86400, False),
]

# Default retention: keep everything indefinitely until the user opts into pruning (§31).
RETENTION_DEFAULTS = [
    'icmp', 'dns', 'http', 'tcp', 'route', 'mtu', 'throughput', 'bufferbloat', 'interface',
]


def seed_defaults(apps, schema_editor):
    ScheduleConfig = apps.get_model('core', 'ScheduleConfig')
    RetentionPolicy = apps.get_model('core', 'RetentionPolicy')

    for task_type, interval_seconds, enabled in SCHEDULE_DEFAULTS:
        ScheduleConfig.objects.get_or_create(
            task_type=task_type,
            defaults={'interval_seconds': interval_seconds, 'enabled': enabled},
        )

    for data_type in RETENTION_DEFAULTS:
        RetentionPolicy.objects.get_or_create(data_type=data_type)


def remove_defaults(apps, schema_editor):
    ScheduleConfig = apps.get_model('core', 'ScheduleConfig')
    RetentionPolicy = apps.get_model('core', 'RetentionPolicy')
    ScheduleConfig.objects.filter(
        task_type__in=[t for t, _, _ in SCHEDULE_DEFAULTS]
    ).delete()
    RetentionPolicy.objects.filter(data_type__in=RETENTION_DEFAULTS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_defaults, remove_defaults),
    ]
