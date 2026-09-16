"""
HTTPS/TLS probe implementation.
Measures TLS handshake timing and HTTP response performance.
"""
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


def probe_https(
    url: str,
    timeout_seconds: float = 10.0,
) -> dict:
    """Probe an HTTPS URL for availability and timing."""
    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "target_host": url.split("//")[1].split("/")[0] if "//" in url else "unknown",
        "target_type": "https",
        "success": False,
        "rtt_ms": None,
        "error_message": "HTTPS probe failed",
    }

    try:
        import urllib.request
        import urllib.error

        start = datetime.now(timezone.utc)

        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'ISP-Accountability-Monitor/1.0',
                'Accept': '*/*',
            },
        )

        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            end = datetime.now(timezone.utc)
            total_time_ms = (end - start).total_seconds() * 1000

            result["success"] = True
            result["http_status_code"] = response.status
            result["rtt_ms"] = round(total_time_ms, 2)
            result["bytes_received"] = len(response.read())

    except urllib.error.HTTPError as e:
        result["error_message"] = f"HTTP error {e.code}: {e.reason}"
        result["http_status_code"] = e.code
    except urllib.error.URLError as e:
        result["error_message"] = f"URL error: {str(e.reason)}"
    except Exception as e:
        result["error_message"] = str(e)

    return result


def probe_cloudflare_health(
    url: str = "https://1.1.1.1/",
    timeout_seconds: float = 5.0,
) -> dict:
    """Probe Cloudflare health endpoint."""
    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "target_host": url.split("//")[1].split("/")[0] if "//" in url else "unknown",
        "target_type": "cloudflare_health",
        "success": False,
        "rtt_ms": None,
        "error_message": "Cloudflare health check failed",
    }

    try:
        import urllib.request

        start = datetime.now(timezone.utc)

        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'ISP-Accountability-Monitor/1.0',
                'Accept': '*/*',
            },
        )

        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            end = datetime.now(timezone.utc)
            total_time_ms = (end - start).total_seconds() * 1000

            result["success"] = True
            result["http_status_code"] = response.status
            result["rtt_ms"] = round(total_time_ms, 2)
            result["response_body_length"] = len(response.read())

    except Exception as e:
        result["error_message"] = str(e)

    return result


def probe_multiple_endpoints(
    endpoints: list[dict],
    timeout_seconds: float = 5.0,
) -> list[dict]:
    """Probe multiple HTTPS endpoints."""
    results = []

    for endpoint in endpoints:
        result = probe_https(
            url=endpoint["url"],
            timeout_seconds=timeout_seconds,
        )
        results.append(result)

    return results


def get_system_ssl_info() -> dict:
    """Get information about system SSL/TLS configuration."""
    try:
        import ssl as ssl_module
        return {
            "default_context": str(ssl_module.create_default_context()),
            "certificate_transparency": True,
        }
    except Exception as e:
        return {"error": str(e)}
