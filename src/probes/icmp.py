"""
ICMP (ping) probe implementation for cross-platform monitoring.
Uses subprocess to call native ping command (works on Windows/Linux).
Falls back to TCP-based health checks when ICMP is blocked by firewall.
"""
import platform
import socket
import subprocess
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


def _run_ping_command(host: str, count: int = 4) -> dict:
    """Run native ping command and parse results."""
    # Cross-platform ping command
    if platform.system() == "Windows":
        cmd = ["ping", "-n", str(count), "-w", "2000", host]
    else:
        cmd = ["ping", "-c", str(count), "-W", "2", host]

    result = {
        "target_host": host,
        "count": count,
        "success": False,
        "rtt_ms": None,
        "packet_loss_count": count,
        "error_message": "Command not found or ICMP blocked",
    }

    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )

        output = process.stdout + process.stderr
        lines = output.strip().split("\n")

        if process.returncode != 0:
            result["error_message"] = f"Ping failed with exit code {process.returncode}"
            return result

        # Parse ping statistics
        import re
        stats_line = next((l for l in lines if "bytes" in l.lower() and ("packets" in l.lower() or "%" in l.lower())), None)

        if not stats_line:
            return result

        try:
            loss_match = re.search(r"(\d+)\s+percent\s+loss", stats_line, re.IGNORECASE)
            rtt_match = re.search(r"rtt\s*min/avg/max/mdev\s*=\s*(\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)",
                                  stats_line, re.IGNORECASE)

            if loss_match:
                result["packet_loss_count"] = int(loss_match.group(1)) * count // 100
                result["success"] = result["packet_loss_count"] == 0

            if rtt_match and result["success"]:
                rtt_values = [float(x) for x in rtt_match.groups()[1:4]]
                result["rtt_ms"] = round(min(rtt_values), 2)

        except Exception:
            pass

    except subprocess.TimeoutExpired:
        result["error_message"] = "Ping timed out"
    except FileNotFoundError:
        result["error_message"] = "ping command not found (firewall may be blocking ICMP)"
    except Exception as e:
        result["error_message"] = str(e)

    return result


async def ping_target(
    host: str,
    count: int = 4,
    timeout_ms: int = 5000,
) -> dict:
    """Perform ICMP ping measurement asynchronously."""
    utc_ts, local_ts = get_timestamps()
    result = {
        "timestamp_utc": utc_ts,
        "timestamp_local": local_ts,
        **_run_ping_command(host, count),
    }
    return result


def probe_gateway(
    interface_name: str | None = None,
    count: int = 3,
) -> dict:
    """Probe default gateway reachability."""
    import psutil

    # Try to determine actual gateway IP (may differ from interface name)
    gateway_ip = None
    for iface in psutil.net_if_addrs().values():
        if isinstance(iface, dict):
            for add in iface.values():
                if hasattr(add, 'netmask'):
                    try:
                        netmask = str(add.netmask)
                        if len(netmask) > 8 and "docker" not in str(iface):
                            gateway_ip = add.address
                            break
                    except Exception:
                        pass
                elif len(str(add.get('netmask', ''))) > 8:
                    try:
                        gateway_ip = add.address
                        break
                    except Exception:
                        pass

    if not gateway_ip:
        # Fallback to known DNS servers as proxy for "upstream" health
        gateway_ip = "1.1.1.1"

    return _run_ping_command(gateway_ip, count)


def probe_with_tcp_fallback(
    host: str,
    port: int = 80,
    timeout_seconds: float = 2.0,
) -> dict:
    """Probe host with TCP fallback when ICMP unavailable."""
    result = {
        "target_host": host,
        "target_type": "tcp_fallback",
        "success": False,
        "rtt_ms": None,
        "packet_loss_count": 0,
        "error_message": None,
    }

    try:
        sock = socket.create_connection((host, port), timeout=timeout_seconds)
        sock.close()
        result["success"] = True
        result["target_type"] = "tcp"
        result["packet_loss_count"] = 0

    except socket.timeout:
        result["error_message"] = f"TCP connection to {host}:{port} timed out"
    except ConnectionRefusedError:
        result["error_message"] = f"Connection refused by {host}:{port}"
    except Exception as e:
        result["error_message"] = str(e)

    return result
