"""
Background monitoring task for continuous network measurements.
Runs as a FastAPI background task or standalone script.
"""
import asyncio
from datetime import datetime, timezone

try:
    import psutil
except ImportError:
    psutil = None


def get_timestamps(utc_only: bool = False) -> tuple[str, str]:
    """Get current UTC and local timestamps."""
    now = datetime.now(timezone.utc)
    utc_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    if not utc_only:
        local_ts = now.strftime("%Y-%m-%d %H:%M:%S%Z")
    else:
        local_ts = utc_ts
    return utc_ts, local_ts


def get_interface_info() -> dict:
    """Get current network interface information."""
    try:
        result = {
            "interface_name": None,
            "interface_type": "unknown",
        }

        if not psutil:
            return result

        for iface_name, addrs in psutil.net_if_addrs().items():
            if "lo" in iface_name or "docker" in iface_name or "veth" in iface_name:
                continue

            try:
                conn_info = psutil.net_if_stats()[iface_name]
                str_info = str(conn_info)
                result["interface_name"] = iface_name
                if "Wi-Fi" in str_info or "Wireless" in str_info:
                    result["interface_type"] = "wifi"
                else:
                    result["interface_type"] = "ethernet"
                break

            except Exception:
                continue

        return result

    except Exception as e:
        return {
            "error": str(e),
        }


async def run_monitoring_cycle() -> dict:
    """Run one measurement cycle and record results."""
    from probes.icmp import _run_ping_command, probe_gateway_with_tcp_fallback
    from probes.dns import resolve_host
    import socket

    utc_ts, local_ts = get_timestamps()

    result = {
        "timestamp_utc": utc_ts,
        "timestamp_local": local_ts,
        "gateways": [],
        "icmp_results": [],
        "tcp_results": [],
        "dns_results": [],
    }

    # Gateway reachability test
    gateway_result = probe_gateway_with_tcp_fallback("1.1.1.1")
    result["gateways"] = [{"target": "gateway", **gateway_result}]

    # External endpoints
    for target in ["1.1.1.1", "8.8.8.8"]:
        icmp_result = _run_ping_command(target, count=4)
        result["icmp_results"].append({"host": target, **icmp_result})

        # TCP fallback if ICMP failed
        if not icmp_result.get("success"):
            try:
                sock = socket.create_connection((target, 443), timeout=2.0)
                sock.close()
                result["tcp_results"].append({
                    "host": target,
                    "success": True,
                    "error_message": None,
                })
            except Exception:
                result["tcp_results"].append({
                    "host": target,
                    "success": False,
                    "error_message": "TCP connection failed",
                })

    # DNS tests
    dns_result = resolve_host("cloudflare-dns.com")
    result["dns_results"] = [dns_result]

    return result


def run_monitoring_loop(
    interval_seconds: float = 2.0,
) -> None:
    """Run continuous monitoring loop."""
    while True:
        try:
            result = asyncio.run(run_monitoring_cycle())
            # Store result in database (would need repository import)
            print(f"[{result['timestamp_utc']}] Measurement complete")

        except Exception as e:
            print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Error: {e}")

        # Wait for next interval
        asyncio.run(asyncio.sleep(interval_seconds))
