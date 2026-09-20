"""Detects whether the current process has Administrator privileges (Windows only).

Full-fidelity ICMP (raw sockets) and some interface statistics require elevation (see
docs/DECISIONS.md); the dashboard/worker surface this status so degraded-but-not-broken behavior is
understood rather than mysterious, instead of silently failing probes.
"""
import ctypes
import sys


def is_elevated():
    """Returns True/False on Windows, or None if elevation doesn't apply/can't be determined."""
    if sys.platform != 'win32':
        return None
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return None
