"""On-demand throughput probe via speedtest-cli (§9 — never run continuously by default)."""
import time

import speedtest


def run_throughput_probe(test_type='bidirectional'):
    start = time.monotonic()
    try:
        st = speedtest.Speedtest()
        st.get_best_server()

        mbps_down = st.download() / 1_000_000 if test_type in ('download', 'bidirectional') else None
        mbps_up = st.upload() / 1_000_000 if test_type in ('upload', 'bidirectional') else None

        server = st.results.server
        return {
            'mbps_down': mbps_down,
            'mbps_up': mbps_up,
            'duration_s': time.monotonic() - start,
            'endpoint': server.get('host', ''),
            'error': '',
        }
    except Exception as exc:
        # speedtest-cli raises a mix of its own exceptions and plain socket/URL errors; any of them
        # means "test failed" and should be recorded, not crash the worker (see docs/PHASES.md).
        return {
            'mbps_down': None, 'mbps_up': None, 'duration_s': time.monotonic() - start,
            'endpoint': '', 'error': str(exc),
        }
