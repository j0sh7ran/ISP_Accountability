"""HTTP(S) timing probe. Pure function — see docs/PHASES.md testing strategy (mockable, no real net).

DNS/connect/TLS phases are timed with raw socket/ssl calls (on a throwaway connection) since the
`requests` library doesn't expose that breakdown; the actual HTTP semantics (status/redirects/ttfb)
come from `requests` itself.
"""
import socket
import ssl
import time
from urllib.parse import urlsplit

import requests


def run_http_probe(url, timeout=5):
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == 'https' else 80)

    result = {
        'dns_time_ms': None, 'connect_time_ms': None, 'tls_time_ms': None,
        'ttfb_ms': None, 'total_time_ms': None, 'status_code': None,
        'redirect_count': 0, 'error_type': '',
    }
    overall_start = time.monotonic()

    try:
        dns_start = time.monotonic()
        socket.getaddrinfo(host, port)
        result['dns_time_ms'] = (time.monotonic() - dns_start) * 1000
    except socket.gaierror:
        result['error_type'] = 'dns_error'
        result['total_time_ms'] = (time.monotonic() - overall_start) * 1000
        return result

    try:
        connect_start = time.monotonic()
        sock = socket.create_connection((host, port), timeout=timeout)
        result['connect_time_ms'] = (time.monotonic() - connect_start) * 1000
        if parts.scheme == 'https':
            tls_start = time.monotonic()
            context = ssl.create_default_context()
            with context.wrap_socket(sock, server_hostname=host):
                result['tls_time_ms'] = (time.monotonic() - tls_start) * 1000
        else:
            sock.close()
    except (socket.timeout, TimeoutError):
        result['error_type'] = 'connect_timeout'
        result['total_time_ms'] = (time.monotonic() - overall_start) * 1000
        return result
    except ConnectionRefusedError:
        result['error_type'] = 'connection_refused'
        result['total_time_ms'] = (time.monotonic() - overall_start) * 1000
        return result
    except OSError:
        result['error_type'] = 'connection_error'
        result['total_time_ms'] = (time.monotonic() - overall_start) * 1000
        return result

    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        result['ttfb_ms'] = response.elapsed.total_seconds() * 1000
        result['status_code'] = response.status_code
        result['redirect_count'] = len(response.history)
    except requests.Timeout:
        result['error_type'] = 'timeout'
    except requests.ConnectionError:
        result['error_type'] = 'connection_error'
    except requests.RequestException:
        result['error_type'] = 'request_error'

    result['total_time_ms'] = (time.monotonic() - overall_start) * 1000
    return result
