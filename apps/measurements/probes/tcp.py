"""TCP connect probe. Pure function — see docs/PHASES.md testing strategy (mockable, no real net)."""
import socket
import time


def run_tcp_probe(address, port, timeout=3):
    start = time.monotonic()
    try:
        sock = socket.create_connection((address, port), timeout=timeout)
        connect_time_ms = (time.monotonic() - start) * 1000
        sock.close()
        return {'success': True, 'error_type': '', 'connect_time_ms': connect_time_ms}
    except socket.timeout:
        return {'success': False, 'error_type': 'timeout', 'connect_time_ms': None}
    except ConnectionRefusedError:
        return {'success': False, 'error_type': 'refused', 'connect_time_ms': None}
    except ConnectionResetError:
        return {'success': False, 'error_type': 'reset', 'connect_time_ms': None}
    except OSError:
        return {'success': False, 'error_type': 'error', 'connect_time_ms': None}
