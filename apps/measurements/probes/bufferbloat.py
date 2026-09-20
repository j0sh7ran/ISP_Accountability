"""Bufferbloat probe (§11): compares idle vs. load-induced ICMP latency.

`classification` is descriptive only — the raw baseline/loaded/recovery fields are what should be
independently reviewed, per docs/REPORTING_AND_RETENTION.md and docs/STATE_MACHINE_AND_INCIDENTS.md.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from .icmp import run_icmp_probe
from .throughput import run_throughput_probe


def _classify(latency_increase_ms):
    if latency_increase_ms is None:
        return 'unclassified'
    if latency_increase_ms < 30:
        return 'none'
    if latency_increase_ms < 100:
        return 'moderate'
    return 'severe'


def run_bufferbloat_probe(icmp_address, count=5):
    baseline = run_icmp_probe(icmp_address, count=count)
    baseline_rtt_ms = baseline['avg_rtt_ms'] or 0.0

    with ThreadPoolExecutor(max_workers=1) as executor:
        throughput_future = executor.submit(run_throughput_probe, 'bidirectional')
        loaded = run_icmp_probe(icmp_address, count=count)
        throughput_result = throughput_future.result()

    recovery_start = time.monotonic()
    run_icmp_probe(icmp_address, count=count)
    recovery_time_s = time.monotonic() - recovery_start

    loaded_rtt_ms = loaded['avg_rtt_ms']
    latency_increase_ms = (loaded_rtt_ms - baseline_rtt_ms) if loaded_rtt_ms is not None else None

    return {
        'baseline_rtt_ms': baseline_rtt_ms,
        'loaded_rtt_download_ms': None,
        'loaded_rtt_upload_ms': None,
        'loaded_rtt_bidirectional_ms': loaded_rtt_ms,
        'loss_during_load_pct': loaded['loss_pct'],
        'throughput_during_load_mbps': throughput_result.get('mbps_down'),
        'recovery_time_s': recovery_time_s,
        'classification': _classify(latency_increase_ms),
    }
