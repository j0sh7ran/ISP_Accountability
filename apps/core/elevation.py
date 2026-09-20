"""Detects whether the current process has elevated privileges — Administrator on Windows, root on
Linux/macOS.

Full-fidelity ICMP (raw sockets), route tracing, and MTU discovery may need elevation on some
platforms (see docs/DECISIONS.md); the dashboard/worker surface this status so degraded-but-not-
broken behavior is understood rather than mysterious, instead of silently failing probes.
"""
import ctypes
import os
import sys


def is_elevated():
    """Returns True/False, or None if it can't be determined on this platform."""
    if sys.platform == 'win32':
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return None
    if sys.platform in ('linux', 'darwin'):
        try:
            return os.geteuid() == 0
        except (AttributeError, OSError):
            return None
    return None

