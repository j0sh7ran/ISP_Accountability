"""
TCP connectivity probe implementation.
Tests TCP connection establishment timing and success/failure.
"""
import socket
from datetime import datetime, timezone


def get_timestamps(utc_only: bool = False) -> tuple[str, str]:
    """Get current UTC and local timestamps."""
    now = datetime.now(timezone.utc)
    utc_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not utc_only:
        local_ts = now.strftime("%Y-%m-%d %H:%M:%S%Z")
    else:
        local_ts = utc_ts
    return utc_ts, local_ts


def probe_tcp_connect(
    host: str,
    port: int,
    timeout_seconds: float = 2.0,
) -> dict:
    """Test TCP connection to a host:port."""
    utc_ts, local_ts = get_timestamps()

    result = {
        "timestamp_utc": utc_ts,
        "timestamp_local": local_ts,
        "target_host": host,
        "target_type": "tcp",
        "success": False,
        "rtt_ms": None,
        "error_message": "TCP connection failed or timed out",
    }

    try:
        start = datetime.now(timezone.utc)

        # Create socket and connect
        sock = socket.create_connection(
            (host, port),
            timeout=timeout_seconds,
        )

        end = datetime.now(timezone.utc)
        total_time_ms = (end - start).total_seconds() * 1000

        result["success"] = True
        result["socket_established"] = True
        result["rtt_ms"] = round(total_time_ms, 2)
        result["host"] = host
        result["port"] = port

        sock.close()

    except socket.timeout:
        result["error_message"] = f"TCP connection to {host}:{port} timed out after {timeout_seconds}s"
    except ConnectionRefusedError:
        result["error_message"] = f"Connection refused by {host}:{port}"
    except socket.gaierror as e:
        result["error_message"] = f"DNS lookup failed for {host}: {str(e)}"
    except Exception as e:
        result["error_message"] = f"Error connecting to {host}:{port}: {str(e)}"

    return result


def probe_https_endpoint(
    host: str,
    url: Optional[str] = None,
    timeout_seconds: float = 10.0,
) -> dict:
    """Probe an HTTPS endpoint for TLS health."""
    import urllib.request

    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "target_host": host,
        "target_type": "https",
        "success": False,
        "rtt_ms": None,
        "error_message": "HTTPS probe failed",
    }

    try:
        start = datetime.now(timezone.utc)

        if not url:
            url = f"https://{host}/"

        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'ISP-Accountability-Monitor'},
        )

        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            result["success"] = True
            result["http_status_code"] = response.status
            result["response_time_ms"] = round((datetime.now(timezone.utc) - start).total_seconds() * 1000, 2)

    except urllib.error.HTTPError as e:
        result["error_message"] = f"HTTP error {e.code} from {host}"
        result["http_status_code"] = e.code
    except urllib.error.URLError as e:
        result["error_message"] = f"URL error: {str(e.reason)}"
    except Exception as e:
        result["error_message"] = str(e)

    return result


def probe_tcp_port_scan(
    host: str,
    ports: list[int],
    timeout_seconds: float = 1.0,
) -> dict:
    """Probe multiple TCP ports on a host."""
    results = []

    for port in ports:
        result = probe_tcp_connect(host, port, timeout_seconds)
        result["port"] = port
        results.append(result)

    success_count = sum(1 for r in results if r.get("success"))
    total_ports = len(ports)

    return {
        "host": host,
        "results": results,
        "open_ports": [r["port"] for r in results if r.get("success")],
        "blocked_ports": [r["port"] for r in results if not r.get("success")],
        "success_rate": round(success_count / total_ports * 100, 1) if total_ports else 0,
    }


def test_https_handshake(
    host: str,
    timeout_seconds: float = 5.0,
) -> dict:
    """Test HTTPS handshake timing (DNS + TCP + TLS)."""
    import urllib.request

    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "target_host": host,
        "target_type": "https_handshake",
        "success": False,
        "rtt_ms": None,
        "error_message": "HTTPS handshake failed",
    }

    try:
        start = datetime.now(timezone.utc)

        url = f"https://{host}/"
        req = urllib.request.Request(url, headers={'User-Agent': 'ISP-Accountability-Monitor'})

        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            total_time_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            result["success"] = True
            result["rtt_ms"] = round(total_time_ms, 2)
            result["http_status_code"] = response.status

    except Exception as e:
        result["error_message"] = str(e)

    return result


def probe_with_payload(
    host: str,
    port: int = 80,
    payload: bytes = b"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".format(host=host),
    timeout_seconds: float = 2.0,
) -> dict:
    """Send actual HTTP request with small payload."""
    import urllib.request

    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "target_host": host,
        "target_type": "http_request",
        "success": False,
        "rtt_ms": None,
        "error_message": "HTTP request failed",
    }

    try:
        start = datetime.now(timezone.utc)

        url = f"http://{host}"
        req = urllib.request.Request(url)
        req.add_header("Content-Type", "application/octet-stream")

        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            total_time_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            received_bytes = len(response.read())

            result["success"] = True
            result["rtt_ms"] = round(total_time_ms, 2)
            result["http_status_code"] = response.status
            result["bytes_received"] = received_bytes
            result["payload_sent"] = len(payload) if payload else 0

    except Exception as e:
        result["error_message"] = str(e)

    return result


def get_available_ports(
    host: str,
    port_range: tuple[int, int] = (80, 443),
) -> list[dict]:
    """Test which common ports are open on a host."""
    ports_to_test = range(port_range[0], port_range[1] + 1)

    results = []
    for port in ports_to_test:
        result = probe_tcp_connect(host, port, timeout_seconds=0.5)
        result["port"] = port
        results.append(result)

    return {
        "host": host,
        "ports_tested": range(port_range[0], port_range[1] + 1),
        "results": results,
        "open_ports": [r["port"] for r in results if r.get("success")],
        "closed_ports": [r["port"] for r in results if not r.get("success")],
    }
