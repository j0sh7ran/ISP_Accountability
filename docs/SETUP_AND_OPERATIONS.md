# Setup & Operations

Operational guidance for running this application on Windows, Linux, or macOS — installation,
elevation, firewall prompts, and (optional) run-at-startup convenience. For architecture, see
[ARCHITECTURE.md](ARCHITECTURE.md) and the rest of [docs/](README.md).

## Prerequisites

- Windows 10/11, Linux, or macOS.
- Python 3.12+ (developed against 3.14.4; see [DECISIONS.md](DECISIONS.md)).
- No external database server, no internet connection required to run.
- **Linux only:** the `traceroute` package for route tracing (often not preinstalled) —
  `sudo apt install traceroute` (Debian/Ubuntu) or the equivalent for your distro. Windows ships
  `tracert.exe` and macOS ships `traceroute` out of the box, so no extra install is needed there.

## First-time setup

**Windows (PowerShell):**
```powershell
git clone <this repo>
cd ISP_Accountability
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

**Linux / macOS:**
```bash
git clone <this repo>
cd ISP_Accountability
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
```

Then configure at least one `Target` (e.g. your default gateway) via the admin at
`/admin/core/target/` before starting the worker — with no enabled targets there is nothing to probe.

## Running

Two processes run independently (see [ARCHITECTURE.md](ARCHITECTURE.md)):

**Windows:**
```powershell
# Terminal 1 — dashboard (binds to 127.0.0.1 only)
.\.venv\Scripts\python.exe manage.py runserver

# Terminal 2 — measurement worker (run elevated for full ICMP fidelity — see below)
.\.venv\Scripts\python.exe manage.py run_worker
```

**Linux / macOS:**
```bash
# Terminal 1 — dashboard (binds to 127.0.0.1 only)
.venv/bin/python manage.py runserver

# Terminal 2 — measurement worker (run with sudo for full ICMP fidelity — see below)
.venv/bin/python manage.py run_worker
```

Visit `http://127.0.0.1:8000/`.

## Administrator / elevation

Raw ICMP probes (used for latency/loss/jitter) and some interface statistics require the worker
process to run elevated — Administrator on Windows, `root` (e.g. via `sudo`) on Linux/macOS. If
`run_worker` is **not** run elevated:

- It prints a warning at startup and the dashboard shows a "Not running as Administrator"/"Not
  running as root" banner (`apps/core/elevation.py` detects both — Windows via
  `IsUserAnAdmin()`, Linux/macOS via `os.geteuid() == 0`).
- ICMP probes will typically fail with a permission error and be recorded as failed measurements
  (`error` field set) rather than crashing the worker — see [DECISIONS.md](DECISIONS.md).
- All other probe types (DNS, HTTP, TCP, route, MTU, throughput, interface counters) work without
  elevation on all three platforms.

To run elevated: on Windows, right-click PowerShell/Terminal → "Run as administrator", then
re-run `run_worker` from that elevated shell; on Linux/macOS, prefix the command with `sudo`
(e.g. `sudo .venv/bin/python manage.py run_worker`).

## Firewall

The first time probes make outbound connections, Windows may show a firewall prompt — allow it
for both Private and Public networks, otherwise some probes (especially ICMP) may silently fail.
Linux/macOS firewalls (`ufw`, `pf`, etc.) are typically permissive for outbound traffic by
default and rarely need changes for this app's probes.

## Optional: start the worker automatically at login/boot

The worker is a manually-started console process by design (see [DECISIONS.md](DECISIONS.md) —
no OS service was implemented). If you want it to start automatically:

**Windows** — Task Scheduler:
1. Create a `.bat` launcher, e.g. `run_worker.bat` in the project root:
   ```bat
   @echo off
   cd /d %~dp0
   ".venv\Scripts\pythonw.exe" manage.py run_worker
   ```
   (`pythonw.exe` avoids a visible console window; use `python.exe` instead if you want to see output.)
2. Open Task Scheduler → Create Task → Trigger: "At log on" → Action: run the `.bat` file above →
   under General, check "Run with highest privileges" if you want elevated ICMP fidelity.

**Linux** — a systemd user/system service, e.g. `/etc/systemd/system/isp-monitor-worker.service`:
```ini
[Unit]
Description=ISP Network SLA Monitor worker

[Service]
WorkingDirectory=/path/to/ISP_Accountability
ExecStart=/path/to/ISP_Accountability/.venv/bin/python manage.py run_worker
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```
Then `sudo systemctl enable --now isp-monitor-worker`. Drop `User=root` (and don't use `sudo`) if
you don't need elevated ICMP fidelity.

**macOS** — a `launchd` agent, e.g. `~/Library/LaunchAgents/com.isp-monitor.worker.plist`, with
`ProgramArguments` pointing at `.venv/bin/python manage.py run_worker` and `RunAtLoad`/`KeepAlive`
set, loaded via `launchctl load ~/Library/LaunchAgents/com.isp-monitor.worker.plist`.

This is a convenience only — stopping the worker (however it was started) simply stops new
measurements from being collected; nothing else in the application is affected, and it resumes
cleanly whenever it's started again.

## Testing

**Windows:**
```powershell
.\.venv\Scripts\python.exe manage.py test
# or, equivalently:
.\.venv\Scripts\python.exe -m pytest
```

**Linux / macOS:**
```bash
.venv/bin/python manage.py test
# or, equivalently:
.venv/bin/python -m pytest
```

All tests mock outward network I/O (`unittest.mock`/`responses`/subprocess mocking) — the suite
never makes real network calls and does not require elevation to pass, on any platform.

