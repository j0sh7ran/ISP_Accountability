"""MTU/PMTUD probe via a DF-set ping binary search (no scapy/raw packets needed — see
docs/DECISIONS.md). Ping's DF-bit flag, payload-size flag, and success/failure output text all
differ per OS ping implementation, so command-building/parsing is split per platform; `_ping_df` is
isolated so `run_mtu_probe`'s search logic can be unit tested by mocking it, with no real network
access (see docs/PHASES.md testing strategy).
"""
import subprocess
import sys


def _ping_df_command(address, size, timeout_ms):
    if sys.platform == 'win32':
        return ['ping', '-n', '1', '-f', '-l', str(size), '-w', str(timeout_ms), address]
    if sys.platform == 'darwin':
        # BSD ping: -D sets the DF bit, -s is the ICMP payload size, -W is a per-packet timeout (ms).
        return ['ping', '-c', '1', '-D', '-s', str(size), '-W', str(timeout_ms), address]
    # Linux (iputils ping): -M do sets DF, -s is payload size, -W is a response timeout in whole seconds.
    timeout_s = max(1, round(timeout_ms / 1000))
    return ['ping', '-c', '1', '-M', 'do', '-s', str(size), '-W', str(timeout_s), address]


def _ping_success(output):
    if sys.platform == 'win32':
        return 'Reply from' in output and 'TTL=' in output
    return 'bytes from' in output


def _is_fragmentation_needed(output):
    lowered = output.lower()
    if sys.platform == 'win32':
        return 'fragmented' in lowered or 'df set' in lowered
    return 'frag' in lowered or 'message too long' in lowered or 'would fragment' in lowered


def _ping_df(address, size, timeout_ms=2000):
    """Send one DF-set ping of the given ICMP payload size. Returns (success, raw_output)."""
    try:
        proc = subprocess.run(
            _ping_df_command(address, size, timeout_ms),
            capture_output=True, text=True, timeout=(timeout_ms / 1000) + 5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False, ''
    output = proc.stdout + proc.stderr
    return _ping_success(output), output


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
            if _is_fragmentation_needed(output):
                df_behavior = 'df_honored_fragmentation_needed'
            hi = mid - 1

    return {
        'largest_successful_size': largest_ok if largest_ok is not None else 0,
        'df_behavior': df_behavior,
        'pmtud_response': 'fragmentation_needed' if smallest_fail is not None else '',
        'failure_threshold': smallest_fail if smallest_fail is not None else 0,
    }
