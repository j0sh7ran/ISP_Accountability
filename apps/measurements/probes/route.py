"""Route tracing via the OS's native traceroute tool — `tracert.exe` on Windows, `traceroute` on
Linux/macOS (no admin/Npcap/raw sockets needed — see docs/DECISIONS.md). `traceroute` isn't always
preinstalled on Linux (e.g. `apt install traceroute`); see docs/SETUP_AND_OPERATIONS.md.

Both parsers are pure functions so they can be unit tested against captured sample text with no
real network access (see docs/PHASES.md testing strategy).
"""
import re
import subprocess
import sys

HOP_LINE_RE = re.compile(r'^\s*(\d+)\s+(.*)$')


def parse_tracert_output(output):
    """Parse Windows `tracert -d` output into a list of hop dicts."""
    hops = []
    for line in output.splitlines():
        match = HOP_LINE_RE.match(line)
        if not match:
            continue
        hop_number = int(match.group(1))
        rest = match.group(2).strip()

        if 'Request timed out' in rest:
            hops.append(
                {'hop_number': hop_number, 'ip_address': '', 'hostname': '', 'rtt_ms': None, 'timeout': True}
            )
            continue

        tokens = rest.split()
        rtts = []
        i = 0
        while i < len(tokens) - 1:
            if tokens[i] == '*':
                i += 1
                continue
            if tokens[i + 1] == 'ms':
                try:
                    rtts.append(float(tokens[i].lstrip('<')))
                except ValueError:
                    pass
                i += 2
                continue
            i += 1

        ip_address = tokens[-1] if tokens else ''
        hops.append({
            'hop_number': hop_number,
            'ip_address': ip_address,
            'hostname': '',
            'rtt_ms': min(rtts) if rtts else None,
            'timeout': not rtts,
        })
    return hops


def parse_traceroute_output(output):
    """Parse Unix `traceroute -n` output (Linux/macOS) into a list of hop dicts.

    Unlike `tracert -d`, the IP address comes right after the hop number (not last), and a fully
    timed-out hop prints as `* * *` rather than a "Request timed out" message.
    """
    hops = []
    for line in output.splitlines():
        match = HOP_LINE_RE.match(line)
        if not match:
            continue
        hop_number = int(match.group(1))
        tokens = match.group(2).strip().split()

        if not tokens or all(token == '*' for token in tokens):
            hops.append(
                {'hop_number': hop_number, 'ip_address': '', 'hostname': '', 'rtt_ms': None, 'timeout': True}
            )
            continue

        ip_address = next((t for t in tokens if t not in ('*', 'ms') and not t.endswith('ms')), '')
        rtts = []
        i = 0
        while i < len(tokens) - 1:
            if tokens[i + 1] == 'ms':
                try:
                    rtts.append(float(tokens[i]))
                except ValueError:
                    pass
                i += 2
                continue
            i += 1

        hops.append({
            'hop_number': hop_number,
            'ip_address': ip_address,
            'hostname': '',
            'rtt_ms': min(rtts) if rtts else None,
            'timeout': not rtts,
        })
    return hops


def run_traceroute(address, max_hops=30, per_hop_timeout_ms=2000, timeout=30):
    """Runs the platform's traceroute/tracert and returns parsed hops (empty list on failure)."""
    if sys.platform == 'win32':
        command = ['tracert', '-d', '-h', str(max_hops), '-w', str(per_hop_timeout_ms), address]
        parser = parse_tracert_output
    else:
        timeout_s = max(1, round(per_hop_timeout_ms / 1000))
        command = ['traceroute', '-n', '-m', str(max_hops), '-w', str(timeout_s), address]
        parser = parse_traceroute_output

    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return []
    return parser(proc.stdout)
