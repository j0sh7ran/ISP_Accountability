"""MTU/PMTUD probe via a Windows ping.exe -f -l <size> binary search (no scapy/raw packets needed —
see docs/DECISIONS.md). `_ping_df` is isolated so `run_mtu_probe`'s search logic can be unit tested
by mocking it, with no real network access (see docs/PHASES.md testing strategy).
"""
import subprocess


def _ping_df(address, size, timeout_ms=2000):
    """Send one DF-set ping of the given ICMP payload size. Returns (success, raw_output)."""
    try:
        proc = subprocess.run(
            ['ping', '-n', '1', '-f', '-l', str(size), '-w', str(timeout_ms), address],
            capture_output=True, text=True, timeout=(timeout_ms / 1000) + 5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False, ''
    output = proc.stdout
    return ('Reply from' in output and 'TTL=' in output), output


def run_mtu_probe(address, low=1200, high=1500, timeout_ms=2000):
    """Binary-search the largest DF-set ICMP payload size that gets a reply."""
    largest_ok = None
    smallest_fail = None
    df_behavior = 'unknown'

    lo, hi = low, high
    while lo <= hi:
        mid = (lo + hi) // 2
        success, output = _ping_df(address, mid, timeout_ms)
        if success:
            largest_ok = mid
            lo = mid + 1
        else:
            smallest_fail = mid
            if 'fragmented' in output.lower() or 'df set' in output.lower():
                df_behavior = 'df_honored_fragmentation_needed'
            hi = mid - 1

    return {
        'largest_successful_size': largest_ok if largest_ok is not None else 0,
        'df_behavior': df_behavior,
        'pmtud_response': 'fragmentation_needed' if smallest_fail is not None else '',
        'failure_threshold': smallest_fail if smallest_fail is not None else 0,
    }
