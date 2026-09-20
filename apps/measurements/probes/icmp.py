"""ICMP echo probe. Pure function returning a result dict — no Django/DB dependency, so it can be
unit tested by mocking icmplib without any real network access (see docs/PHASES.md testing strategy).
"""
import statistics

from icmplib import ICMPLibError
from icmplib import ping as icmp_ping


def run_icmp_probe(address, count=4, interval=0.2, timeout=2):
    """Send `count` ICMP echo requests to `address` and summarize the results.

    Returns a dict matching the ICMPMeasurement fields (minus target/timestamp/address_family,
    which the caller fills in). On failure (e.g. no ICMP permission, name lookup failure), returns
    a result with received=0 and `error` set instead of raising.
    """
    try:
        host = icmp_ping(address, count=count, interval=interval, timeout=timeout, privileged=True)
    except ICMPLibError as exc:
        return {
            'sent': count,
            'received': 0,
            'loss_pct': 100.0,
            'min_rtt_ms': None,
            'avg_rtt_ms': None,
            'median_rtt_ms': None,
            'max_rtt_ms': None,
            'p95_rtt_ms': None,
            'p99_rtt_ms': None,
            'jitter_ms': None,
            'error': str(exc),
        }

    rtts = sorted(host.rtts)
    return {
        'sent': host.packets_sent,
        'received': host.packets_received,
        'loss_pct': host.packet_loss * 100,
        'min_rtt_ms': host.min_rtt if rtts else None,
        'avg_rtt_ms': host.avg_rtt if rtts else None,
        'median_rtt_ms': statistics.median(rtts) if rtts else None,
        'max_rtt_ms': host.max_rtt if rtts else None,
        'p95_rtt_ms': _percentile(rtts, 95),
        'p99_rtt_ms': _percentile(rtts, 99),
        'jitter_ms': host.jitter if rtts else None,
        'error': '',
    }


def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)
