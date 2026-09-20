"""Connectivity state machine evaluator (§18/§19).

Never declares an outage from a single failed probe — a state transition requires a configurable
number of independent targets to agree, over a configurable number of consecutive probes. See
docs/STATE_MACHINE_AND_INCIDENTS.md.
"""
from django.utils import timezone

from apps.core.models import Target, TargetCategory
from apps.measurements.models import ICMPMeasurement

from .models import ConnectivityState, NetworkStateLog, StateMachineConfig

CONFIRMING_CATEGORIES = [TargetCategory.GATEWAY, TargetCategory.ISP_HOP, TargetCategory.INTERNET]


def _consecutive_failures(target, limit):
    """How many of the most recent (up to `limit`) ICMP measurements for `target` failed in a row."""
    recent = ICMPMeasurement.objects.filter(target=target).order_by('-timestamp')[:limit]
    count = 0
    for measurement in recent:
        if measurement.error or measurement.loss_pct >= 100:
            count += 1
        else:
            break
    return count


def _consecutive_successes(target, limit):
    recent = ICMPMeasurement.objects.filter(target=target).order_by('-timestamp')[:limit]
    count = 0
    for measurement in recent:
        if not measurement.error and measurement.loss_pct < 100:
            count += 1
        else:
            break
    return count


def evaluate_network_state(targets=None, config=None, now=None):
    """Decide the confirmed connectivity state.

    Returns (new_state, reason, confirming_target_names). Does not persist anything — see
    `evaluate_and_log_state` for the side-effecting wrapper used by the worker.
    """
    now = now or timezone.now()
    config = config or StateMachineConfig.get_solo()
    if targets is None:
        targets = list(Target.objects.filter(enabled=True, category__in=CONFIRMING_CATEGORIES))

    current_state = NetworkStateLog.current_state()
    if not targets:
        return current_state, 'no confirming targets configured', []

    fail_streaks = {t.name: _consecutive_failures(t, config.consecutive_failures_for_offline) for t in targets}
    success_streaks = {t.name: _consecutive_successes(t, config.recovery_confirmation_successes) for t in targets}

    severely_failing = [n for n, s in fail_streaks.items() if s >= config.consecutive_failures_for_offline]
    failing = [n for n, s in fail_streaks.items() if s >= config.consecutive_failures_for_degraded]
    first_success = [n for n, s in success_streaks.items() if s >= 1]
    recovered = [n for n, s in success_streaks.items() if s >= config.recovery_confirmation_successes]

    # OFFLINE can be reached from any state once enough independent targets are severely failing.
    if len(severely_failing) >= config.min_independent_targets_failing:
        return (
            ConnectivityState.OFFLINE,
            f'{len(severely_failing)} independent target(s) failing '
            f'{config.consecutive_failures_for_offline}+ consecutive probes',
            severely_failing,
        )

    if current_state == ConnectivityState.OFFLINE:
        if len(first_success) >= config.min_independent_targets_failing:
            return (
                ConnectivityState.RECOVERING,
                f'{len(first_success)} independent target(s) showing initial recovery',
                first_success,
            )
        return current_state, 'still offline — no successful probes yet', []

    if current_state == ConnectivityState.RECOVERING:
        if len(recovered) >= config.min_independent_targets_failing:
            return (
                ConnectivityState.ONLINE,
                f'{len(recovered)} independent target(s) sustained success for '
                f'{config.recovery_confirmation_successes}+ consecutive probes',
                recovered,
            )
        return current_state, 'awaiting sustained recovery confirmation', []

    if len(failing) >= config.min_independent_targets_failing:
        return (
            ConnectivityState.DEGRADED,
            f'{len(failing)} independent target(s) failing {config.consecutive_failures_for_degraded}+ consecutive probes',
            failing,
        )

    if current_state == ConnectivityState.DEGRADED and not failing:
        return ConnectivityState.ONLINE, 'no targets failing', []

    return current_state, 'no state change', []


def evaluate_and_log_state(targets=None, config=None, now=None):
    """Evaluate state and persist a NetworkStateLog row (+ derive incidents) only if it changed."""
    from apps.incidents.derivation import handle_state_transition

    now = now or timezone.now()
    current_state = NetworkStateLog.current_state()
    new_state, reason, confirming = evaluate_network_state(targets=targets, config=config, now=now)
    if new_state == current_state:
        return None

    log = NetworkStateLog.objects.create(
        timestamp=now, previous_state=current_state, new_state=new_state, reason=reason,
        confirming_targets=confirming,
    )
    handle_state_transition(log)
    return log
