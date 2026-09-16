"""
DNS resolution probe implementation.
Measures DNS lookup latency and success rate.
"""
import json
from datetime import datetime, timezone

import socket


def get_timestamps(utc_only: bool = False) -> tuple[str, str]:
    """Get current UTC and local timestamps."""
    now = datetime.now(timezone.utc)
    utc_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not utc_only:
        local_ts = now.strftime("%Y-%m-%d %H:%M:%S%Z")
    else:
        local_ts = utc_ts
    return utc_ts, local_ts


def resolve_host(
    hostname: str,
    resolver: Optional[str] = None,
) -> dict:
    """Resolve a hostname and measure DNS latency."""
    utc_ts, local_ts = get_timestamps()

    result = {
        "timestamp_utc": utc_ts,
        "timestamp_local": local_ts,
        "target_host": hostname,
        "target_type": "dns",
        "success": False,
        "rtt_ms": None,
        "error_message": "DNS resolution failed or resolver unavailable",
    }

    try:
        # If custom resolver specified, configure socket
        if resolver:
            # Try to use specified DNS resolver
            import urllib.request
            headers = {'User-Agent': 'ISP-Accountability-Monitor'}
            req = urllib.request.Request(
                f"https://1.1.1.1/check/dns",
                headers=headers,
                method='GET',
            )
            # Alternative: try nslookup-style query if available
            result["resolver"] = resolver or socket.getdefaultbind()

        start = datetime.now(timezone.utc)

        # Perform DNS resolution
        ip_address = socket.gethostbyname(hostname)

        end = datetime.now(timezone.utc)
        rtt = (end - start).total_seconds() * 1000
        rtt = round(rtt, 2)

        result["success"] = True
        result["rtt_ms"] = rtt
        result["resolved_ip"] = ip_address

    except socket.gaierror as e:
        result["error_message"] = f"DNS resolution failed: {str(e)}"
    except socket.timeout:
        result["error_message"] = "DNS query timed out"
    except Exception as e:
        result["error_message"] = f"Error during DNS resolution: {str(e)}"

    return result


def probe_dns_resolvers(
    resolvers: Optional[list[str]] = None,
) -> list[dict]:
    """Probe multiple DNS resolvers for health."""
    if not resolvers:
        resolvers = [
            "1.1.1.1",      # Cloudflare
            "8.8.8.8",      # Google
            "9.9.9.9",      # Quad9
        ]

    return [resolve_host(f"resolver-{r}", resolver=r) for r in resolvers]


def probe_8443_health(
    host: str = "1.1.1.1",
    port: int = 8443,
) -> dict:
    """Probe Cloudflare's /health endpoint for TLS/DNS health."""
    import urllib.request

    result = {
        "target_host": host,
        "target_type": "https_health",
        "success": False,
        "rtt_ms": None,
        "error_message": "Health check unavailable",
    }

    try:
        start = datetime.now(timezone.utc)

        url = f"https://{host}:{port}/health"
        req = urllib.request.Request(url, headers={'User-Agent': 'ISP-Accountability-Monitor'})

        with urllib.request.urlopen(req, timeout=5) as response:
            result["success"] = True
            result["http_status_code"] = response.status
            result["response_body_length"] = len(response.read())
            end = datetime.now(timezone.utc)
            total_time = (end - start).total_seconds() * 1000
            result["rtt_ms"] = round(total_time, 2)

    except Exception as e:
        result["error_message"] = str(e)

    return result


def get_dns_configuration() -> dict:
    """Get current DNS configuration from system."""
    try:
        import socket

        # Get default resolver
        try:
            addr_info = socket.getaddrinfo("8.8.8.8", 53, family=socket.AF_UNSPEC)
            resolver_ip = addr_info[0][4][0] if addr_info else "unknown"
        except Exception:
            resolver_ip = "unknown"

        return {
            "primary_resolver": resolver_ip,
            "dns_servers": get_system_dns_servers(),
        }
    except Exception:
        return {}


def get_system_dns_servers() -> list[str]:
    """Read DNS servers from system configuration."""
    dns_servers = []

    try:
        import socket

        # Try to read /etc/resolv.conf (Linux/Mac) or Windows registry equivalent
        if __import__("platform").system() != "Windows":
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        name = line.split()[1]
                        if name and len(name) <= 46:  # Valid DNS name length
                            dns_servers.append(name)
        else:
            # Windows - read from registry or socket info
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters")
                try:
                    count, dtype, value = winreg.QueryValueEx(key, "DnsSearchList")
                except WindowsError:
                    pass
            except Exception:
                pass

    except Exception:
        pass

    # Always include known public resolvers as fallback
    if not dns_servers:
        dns_servers = ["1.1.1.1", "8.8.8.8"]

    return dns_servers


def test_dns_consistency(
    hostname: str,
    num_resolutions: int = 3,
) -> dict:
    """Test DNS consistency by resolving multiple times."""
    results = []

    for _ in range(num_resolutions):
        result = resolve_host(hostname)
        results.append({
            "rtt_ms": result.get("rtt_ms"),
            "resolved_ip": result.get("resolved_ip"),
            "success": result.get("success"),
        })

    # Calculate statistics
    rtt_values = [r["rtt_ms"] for r in results if r.get("rtt_ms") is not None]
    ip_addresses = list(set(r["resolved_ip"] for r in results if r.get("resolved_ip")))

    return {
        "hostname": hostname,
        "results": results,
        "avg_rtt_ms": round(sum(rtt_values) / len(rtt_values), 2) if rtt_values else None,
        "max_rtt_ms": round(max(rtt_values), 2) if rtt_values else None,
        "unique_ips_resolved": len(ip_addresses),
        "ip_addresses": ip_addresses,
        "consistent_resolution": len(ip_addresses) == 1 and results[0].get("success") if results else False,
    }
