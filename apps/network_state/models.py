from django.db import models


class ConnectivityState(models.TextChoices):
    ONLINE = 'online', 'Online'
    DEGRADED = 'degraded', 'Degraded'
    OFFLINE = 'offline', 'Offline'
    RECOVERING = 'recovering', 'Recovering'


class StateMachineConfig(models.Model):
    """Editable confirmation thresholds for the connectivity state machine (§19).

    Exactly one row is expected — always access it via `get_solo()`.
    """

    consecutive_failures_for_degraded = models.PositiveIntegerField(
        default=2, help_text='Consecutive failed probes on a target before it counts as "failing"'
    )
    consecutive_failures_for_offline = models.PositiveIntegerField(
        default=4, help_text='Consecutive failed probes on a target before it counts as "severely failing"'
    )
    min_independent_targets_failing = models.PositiveIntegerField(
        default=2, help_text='Number of independent targets that must agree before a transition is confirmed'
    )
    recovery_confirmation_successes = models.PositiveIntegerField(
        default=3, help_text='Consecutive successful probes required to confirm full recovery'
    )
    micro_outage_threshold_seconds = models.PositiveIntegerField(
        default=60, help_text='Outages shorter than this are classified MICRO_OUTAGE instead of OUTAGE'
    )

    class Meta:
        verbose_name = 'State machine configuration'
        verbose_name_plural = 'State machine configuration'

    def __str__(self):
        return 'State machine thresholds'

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class NetworkStateLog(models.Model):
    """A confirmed connectivity state transition, with the evidence that confirmed it (§19)."""

    timestamp = models.DateTimeField()
    previous_state = models.CharField(max_length=10, choices=ConnectivityState.choices)
    new_state = models.CharField(max_length=10, choices=ConnectivityState.choices)
    reason = models.CharField(max_length=255)
    confirming_targets = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.previous_state} -> {self.new_state} @ {self.timestamp:%Y-%m-%d %H:%M:%S}'

    @classmethod
    def current_state(cls):
        latest = cls.objects.order_by('-timestamp').first()
        return latest.new_state if latest else ConnectivityState.ONLINE
