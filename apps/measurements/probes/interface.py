"""Local network interface counters via psutil — no remote target involved."""
import psutil


def collect_interface_metrics():
    """Return one dict per local network interface."""
    io_counters = psutil.net_io_counters(pernic=True)
    if_stats = psutil.net_if_stats()

    results = []
    for name, io in io_counters.items():
        stats = if_stats.get(name)
        results.append({
            'interface_name': name,
            'state': 'up' if (stats and stats.isup) else 'down',
            'link_speed_mbps': stats.speed if (stats and stats.speed > 0) else None,
            'bytes_sent': io.bytes_sent,
            'bytes_received': io.bytes_recv,
            'packets_sent': io.packets_sent,
            'packets_received': io.packets_recv,
            'errors_in': io.errin,
            'errors_out': io.errout,
            'discards': io.dropin + io.dropout,
        })
    return results
