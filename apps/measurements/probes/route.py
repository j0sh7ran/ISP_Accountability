"""Route tracing via Windows tracert.exe (no admin/Npcap needed — see docs/DECISIONS.md).

`parse_tracert_output` is a pure function so it can be unit tested against captured sample text
with no real network access (see docs/PHASES.md testing strategy).
"""
import re
import subprocess

HOP_LINE_RE = re.compile(r'^\s*(\d+)\s+(.*)$')


def parse_tracert_output(output):
    """Parse `tracert -d` output into a list of hop dicts."""
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


def run_traceroute(address, max_hops=30, per_hop_timeout_ms=2000, timeout=30):
    """Run `tracert -d` against `address` and return parsed hops (empty list on failure)."""
    try:
        proc = subprocess.run(
            ['tracert', '-d', '-h', str(max_hops), '-w', str(per_hop_timeout_ms), address],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    return parse_tracert_output(proc.stdout)
