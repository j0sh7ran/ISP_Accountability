"""Standalone measurement worker (see docs/WORKER_AND_SCHEDULING.md).

Runs independently of the Django web process; scheduling intervals come from ScheduleConfig rows
in the database, not hard-coded constants (§17).
"""
from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.elevation import is_elevated
from apps.core.models import ScheduleConfig
from apps.worker.jobs import (
    JOBS,
    ON_DEMAND_TASK_TYPES,
    run_aggregation_job,
    run_monthly_report_job,
    run_retention_job,
    run_sla_periodic_job,
)

# How often on-demand task types (throughput/bufferbloat) check for a pending request when their
# own ScheduleConfig is disabled (the default — see §9). The job body itself decides whether to
# actually run the expensive test; this only controls how quickly a manual trigger gets picked up.
ON_DEMAND_POLL_SECONDS = 30

# SLA rules with a measurement_window_seconds (e.g. monthly availability) aren't tied to any single
# probe category, so they're evaluated on their own fixed interval rather than via ScheduleConfig.
SLA_PERIODIC_INTERVAL_SECONDS = 24 * 60 * 60

# Aggregation/retention are meta-jobs over already-collected data, not probe categories, so they
# also run on their own fixed intervals rather than via ScheduleConfig (see docs/DECISIONS.md).
AGGREGATION_INTERVAL_SECONDS = 60 * 60
RETENTION_INTERVAL_SECONDS = 24 * 60 * 60


class Command(BaseCommand):
    help = 'Runs the measurement worker: schedules and executes network probes on their own process.'

    def handle(self, *args, **options):
        elevated = is_elevated()
        if elevated is False:
            self.stdout.write(self.style.WARNING(
                'Not running as Administrator — raw ICMP probes and some interface statistics may be '
                'degraded. See docs/SETUP_AND_OPERATIONS.md.'
            ))
        elif elevated is True:
            self.stdout.write(self.style.SUCCESS('Running elevated (Administrator).'))

        scheduler = BlockingScheduler(
            executors={'default': APSThreadPoolExecutor(max_workers=8)},
            job_defaults={'coalesce': True, 'max_instances': 1, 'misfire_grace_time': 30},
        )
        registered = self._register_jobs(scheduler)
        if not registered:
            self.stdout.write(self.style.WARNING('No enabled ScheduleConfig rows with a matching job — idling.'))

        scheduler.add_job(
            run_sla_periodic_job, 'interval', seconds=SLA_PERIODIC_INTERVAL_SECONDS,
            id='sla_periodic', next_run_time=timezone.now(),
        )
        registered += 1
        scheduler.add_job(
            run_aggregation_job, 'interval', seconds=AGGREGATION_INTERVAL_SECONDS,
            id='aggregation', next_run_time=timezone.now(),
        )
        registered += 1
        scheduler.add_job(
            run_retention_job, 'interval', seconds=RETENTION_INTERVAL_SECONDS,
            id='retention', next_run_time=timezone.now(),
        )
        registered += 1
        # Not given next_run_time=now() — unlike the fixed-interval jobs above, this should only ever
        # fire for real on the last day of the month, not immediately on every worker startup.
        scheduler.add_job(
            run_monthly_report_job, CronTrigger(day='last', hour=23, minute=55), id='monthly_report',
        )
        registered += 1

        self.stdout.write(self.style.SUCCESS(f'Measurement worker started ({registered} job(s)). Press Ctrl+C to stop.'))
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write('Measurement worker stopped.')

    def _register_jobs(self, scheduler):
        count = 0
        for task_type, job in JOBS.items():
            schedule = ScheduleConfig.objects.filter(task_type=task_type).first()
            scheduled_enabled = bool(schedule and schedule.enabled)

            if task_type in ON_DEMAND_TASK_TYPES:
                interval = schedule.interval_seconds if scheduled_enabled else ON_DEMAND_POLL_SECONDS
            elif not scheduled_enabled:
                continue
            else:
                interval = schedule.interval_seconds

            scheduler.add_job(
                job,
                'interval',
                seconds=interval,
                id=f'{task_type}_probe',
                next_run_time=timezone.now(),
            )
            count += 1
        return count
