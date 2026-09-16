"""
Default gateway reachability probe implementation.
Tests whether the local router/gateway is reachable from this device.
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


def get_default_gateway() -> str | None:
    """Get the default gateway IP address."""
    try:
        import psutil

        # Get primary interface with routing
        for iface_name, addrs in psutil.net_if_addrs().items():
            # Skip loopback and virtual interfaces
            if "lo" in iface_name or "docker" in iface_name or "veth" in iface_name:
                continue

            for addr in addrs:
                if addr.family == socket.AF_INET:
                    try:
                        netmask = addr.netmask
                        # Primary interface typically has /24 or larger
                        if len(netmask) > 8 and len(netmask) < 32:
                            return iface_name

                    except AttributeError:
                        continue

        # Fallback: use first non-loopback interface
        for iface_name, addrs in psutil.net_if_addrs().items():
            if "lo" not in iface_name:
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        return iface_name

    except Exception as e:
        pass

    return None


def probe_gateway(
    interface_name: str | None = None,
    count: int = 3,
    timeout_ms: int = 1000,
) -> dict:
    """Probe default gateway reachability."""
    utc_ts, local_ts = get_timestamps()

    # Try to determine actual gateway IP (may differ from interface name)
    try:
        import psutil
        gateway_ip = None

        for iface_name, addrs in psutil.net_if_addrs().items():
            if iface_name != interface_name:  # Don't match by name alone
                continue

            for addr in addrs:
                if addr.family == socket.AF_INET:
                    netmask = str(addr.netmask) if hasattr(addr, 'netmask') else ""
                    # Gateway is typically on the same subnet
                    if len(netmask) > 8:  # /8 or larger (substantial netmask)
                        gateway_ip = addr.address
                        break

        if not gateway_ip:
            # Try to use DNS resolver IP as proxy for "upstream" connectivity
            gateway_ip = "1.1.1.1"  # Cloudflare DNS as upstream indicator

    except Exception as e:
        gateway_ip = None

    result = {
        "timestamp_utc": utc_ts,
        "timestamp_local": local_ts,
        "interface_type": "wifi" if "Wi-Fi" in str(psutil.net_if_addrs() or {}).get(interface_name or "", "") else "ethernet",
        "target_host": f"gateway-{interface_name or 'unknown'}" if gateway_ip else "unknown-gateway",
        "target_type": "icmp",
        "success": False,
        "rtt_ms": None,
        "packet_loss_count": count,
        "error_message": "Could not determine gateway",
    }

    if gateway_ip:
        # Use TCP fallback if ICMP blocked
        result.update(probe_with_tcp_fallback(gateway_ip, port=80))

    return result


def probe_gateway_with_icmp(
    host: str,
    count: int = 4,
    timeout_ms: int = 2000,
) -> dict:
    """Attempt ICMP ping to gateway (if available)."""
    import subprocess

    # Windows/Linux native ping command
    try:
        import platform
        system = platform.system()

        cmd = [
            "ping",
            "-n", str(count),  # Windows: number of packets
            "-w", str(timeout_ms),  # Windows: timeout in ms
            host,
        ] if system == "Windows" else [
            "ping",
            "-c", str(count),  # Linux/Mac: packet count
            "-W", str(timeout_ms // 1000),  # Linux: timeout in seconds
            host,
        ]

        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=count * (timeout_ms / 1000 + 1),
            creationflags=subprocess.CREATE_NO_WINDOW if system == "Windows" else None,
        )

        output = process.stdout + process.stderr
        result = {
            "timestamp_utc": get_timestamps()[0],
            "timestamp_local": get_timestamps()[1],
            "target_host": host,
            "target_type": "icmp_gateway",
            "count": count,
            "success": False,
            "rtt_ms": None,
            "packet_loss_count": 0,
            "error_message": str(process.returncode),
        }

        if process.returncode != 0:
            result["error_message"] = f"Ping failed with exit code {process.returncode}: {output[:200]}"
        else:
            # Parse ping output for statistics
            import re
            lines = output.split("\n")
            stats_line = None

            for line in lines:
                if "bytes" in line.lower() and ("packets" in line.lower() or "%" in line):
                    stats_line = line
                    break

            if stats_line:
                try:
                    # Packet loss percentage
                    loss_match = re.search(r"(\d+)\s+percent\s+loss", stats_line, re.IGNORECASE)
                    if loss_match:
                        result["packet_loss_count"] = int(loss_match.group(1)) * count // 100
                        result["success"] = result["packet_loss_count"] == 0

                    # RTT statistics: rtt min/avg/max/mdev = X/Y/Z/W ms
                    rtt_match = re.search(r"rtt\s*min/avg/max/mdev\s*=\s*(\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)",
                                          stats_line, re.IGNORECASE)
                    if rtt_match and result["success"]:
                        rtt_values = [float(x) for x in rtt_match.groups()[1:4]]
                        result["rtt_ms"] = min(rtt_values)

                except Exception:
                    pass

        return result

    except subprocess.TimeoutExpired:
        return {
            "timestamp_utc": get_timestamps()[0],
            "timestamp_local": get_timestamps()[1],
            "target_host": host,
            "target_type": "icmp_gateway",
            "count": count,
            "success": False,
            "rtt_ms": None,
            "packet_loss_count": count,
            "error_message": "Ping timed out (ICMP blocked or gateway unreachable)",
        }

    except FileNotFoundError:
        return {
            "timestamp_utc": get_timestamps()[0],
            "timestamp_local": get_timestamps()[1],
            "target_host": host,
            "target_type": "icmp_gateway",
            "count": count,
            "success": False,
            "rtt_ms": None,
            "packet_loss_count": count,
            "error_message": "ping command not found",
        }

    except Exception as e:
        return {
            "timestamp_utc": get_timestamps()[0],
            "timestamp_local": get_timestamps()[1],
            "target_host": host,
            "target_type": "icmp_gateway",
            "count": count,
            "success": False,
            "rtt_ms": None,
            "packet_loss_count": count,
            "error_message": str(e),
        }


def probe_with_tcp_fallback(
    host: str,
    port: int = 80,
) -> dict:
    """Use TCP connection as fallback when ICMP unavailable."""
    import socket

    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "target_host": host,
        "target_type": "tcp_gateway_fallback",
        "success": False,
        "rtt_ms": None,
        "packet_loss_count": 0,
        "error_message": "TCP fallback failed",
    }

    try:
        start = datetime.now(timezone.utc)
        sock = socket.create_connection((host, port), timeout=2.0)
        end = datetime.now(timezone.utc)

        result["success"] = True
        result["rtt_ms"] = round((end - start).total_seconds() * 1000, 2)
        result["packet_loss_count"] = 0

    except Exception as e:
        result["error_message"] = str(e)

    return result


def get_gateway_status() -> dict:
    """Get overall gateway health status."""
    result = {
        "timestamp_utc": get_timestamps()[0],
        "timestamp_local": get_timestamps()[1],
        "gateway_reachable": False,
        "interface_type": None,
        "gateway_ip": None,
    }

    interface_name = get_default_gateway()
    if not interface_name:
        result["error_message"] = "Could not determine gateway interface"
        return result

    result["interface_type"] = "wifi" if "Wi-Fi" in str(psutil.net_if_addrs()) else "ethernet"
    result["gateway_ip"] = get_default_gateway()

    # Probe gateway
    probe_result = probe_gateway(interface_name)
    result.update(probe_result)

    return result


def test_multiple_gateways(
    gateways: list[dict],
) -> list[dict]:
    """Test multiple gateway/endpoint combinations."""
    results = []

    for gw in gateways:
        result = probe_gateway(gw.get("interface_name"), gw.get("count", 3))
        result["gateway_config"] = gw
        results.append(result)

    return results


def get_network_adapter_info(
    adapter_name: str | None = None,
) -> dict:
    """Get network adapter information including interface type."""
    try:
        import psutil
        import platform

        result = {
            "adapter_name": adapter_name or next(iter(psutil.net_if_addrs().keys()), "unknown"),
            "platform": platform.system(),
            "is_wireless": False,
            "link_speed_mbps": None,
            "mac_address": None,
        }

        for iface_name, addresses in psutil.net_if_addrs().items():
            if adapter_name and iface_name != adapter_name:
                continue

            try:
                stats = psutil.net_if_stats()[iface_name]
                result["is_wireless"] = "wireless" in str(stats).lower() or "etherdown" not in str(stats).lower()

                # Try to get link speed from netbox if available
                try:
                    import netifaces  # type: ignore
                    config = netifaces.ifconfig(iface_name)
                    result["link_speed_mbps"] = config.get("speed", None)
                except ImportError:
                    pass

            except Exception as e:
                pass

        return result

    except Exception as e:
        return {"error": str(e)}
