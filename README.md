# ISP Accountability Monitor

Local network monitoring tool that collects evidence of ISP connectivity issues and SLA breach analysis. No cloud dependency - runs entirely on your device.

## Quick Start

### Installation

```bash
cd ISP_Accountability
python -m venv venv
.\venv\Scripts\activate    # Windows
# or source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

### Launch

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

The web dashboard will be available at `http://localhost:8000` or `http://<your-IP>:8000` for remote access.

## Features

- **Continuous Monitoring**: Ping, DNS, TCP, HTTPS health checks every 2 seconds
- **Automatic Outage Detection**: Classifies outages as local vs upstream/ISP issues  
- **SLA Analysis**: Configurable SLA policies with breach calculation
- **Evidence Preservation**: Raw measurements retained for audit trail
- **Professional Reports**: PDF/CSV/JSON reports for property management escalation

## Dashboard Overview

### Connection Status
- Gateway reachability (default router)
- External connectivity status
- DNS resolution health
- Current network interface type (Wi-Fi/Ethernet)

### Network Metrics
- Latency (RTT) in milliseconds
- Packet loss percentage
- Jitter measurements

### SLA Utilization
- Configured availability target (e.g., 99.99%)
- Today's downtime total
- Remaining uptime budget

### Recent Outages
- Timeline of detected incidents
- Duration and severity classification
- Evidence confidence indicators

## Actions

- **Run Tests Now**: Manually trigger all probes immediately
- **Generate Report**: Create evidence report (JSON/PDF) for escalation

## Architecture

```
ISP_Accountability/
├── src/
│   ├── main.py              # FastAPI application entrypoint
│   ├── probes/              # Network probe implementations
│   │   ├── icmp.py         # ICMP ping tests
│   │   ├── dns.py          # DNS resolution tests
│   │   ├── tcp.py          # TCP connectivity tests
│   │   └── gateway.py      # Gateway reachability
│   ├── detection/           # Outage detection logic
│   ├── sla/                 # SLA policy engine
│   ├── storage/             # Database models/repositories
│   └── tasks/               # Background monitoring tasks
├── web/                     # Web dashboard files
├── config/                  # Application configuration
├── data/                    # SQLite database
├── exports/                 # Generated reports
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Configuration

Edit `config/default_config.json`:

```json
{
  "probes": {
    "interval_seconds": 2,           // Probe frequency
    "icmp": {
      "targets": ["1.1.1.1", ...]   // Custom endpoints
    }
  },
  "sla": {
    "availability_target": 99.99     // SLA target percentage
  }
}
```

## Evidence Chain

The tool collects and preserves:

1. **Raw measurements**: Every probe result (success/failure, RTT)
2. **Gateway status**: Whether local router is reachable  
3. **Multiple targets**: Multiple independent endpoints tested
4. **Timestamps**: UTC + local timezone for all events
5. **Interface info**: Wi-Fi SSID/BSSID when available

This enables evidence classification:
- `Local-only failure`: Gateway unreachable → local Wi-Fi issue
- `Probable upstream`: Gateway OK + multiple targets fail → ISP/property issue  
- `Endpoint-specific`: Single target fails → likely destination problem

## Privacy

- No cloud dependency
- No mandatory telemetry
- All data stored locally
- No external dependencies required for core functionality

## Escalation Support

Reports include:
- Executive summary of incidents
- Measurement methodology documentation  
- Evidence chain for each outage
- Questions list for vendor escalation

Example questions:
1. What uptime/service-level commitment applies to your service?
2. How are outages defined and measured?
3. What response/restoration times are guaranteed?

## License

Proprietary - for personal use only.
