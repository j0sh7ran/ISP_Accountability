"""DNS resolution probe. Pure function — see docs/PHASES.md testing strategy (mockable, no real DNS)."""
import time

import dns.exception
import dns.resolver


def run_dns_probe(resolver_address, query_name, query_type='A', timeout=2):
    """Query `query_name` against the resolver at `resolver_address` and summarize the result."""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [resolver_address]
    resolver.timeout = timeout
    resolver.lifetime = timeout

    start = time.monotonic()
    try:
        answer = resolver.resolve(query_name, query_type)
        elapsed_ms = (time.monotonic() - start) * 1000
        resolved_ip = answer[0].to_text() if len(answer) else ''
        return {'resolution_time_ms': elapsed_ms, 'result_type': 'success', 'resolved_ip': resolved_ip}
    except dns.resolver.NXDOMAIN:
        return {'resolution_time_ms': None, 'result_type': 'nxdomain', 'resolved_ip': ''}
    except dns.resolver.NoNameservers:
        return {'resolution_time_ms': None, 'result_type': 'servfail', 'resolved_ip': ''}
    except dns.exception.Timeout:
        return {'resolution_time_ms': None, 'result_type': 'timeout', 'resolved_ip': ''}
    except dns.exception.DNSException:
        return {'resolution_time_ms': None, 'result_type': 'error', 'resolved_ip': ''}
