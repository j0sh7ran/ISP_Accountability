# Setup & Operations

Operational guidance for running this application on a Windows device — installation, elevation,
firewall prompts, and (optional) run-at-logon convenience. For architecture, see
[ARCHITECTURE.md](ARCHITECTURE.md) and the rest of [docs/](README.md).

## Prerequisites

- Windows 10/11.
- Python 3.12+ (developed against 3.14.4; see [DECISIONS.md](DECISIONS.md)).
- No external database server, no internet connection required to run.

## First-time setup

```powershell
git clone <this repo>
cd ISP_Accountability
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Then configure at least one `Target` (e.g. your default gateway) via the admin at
`/admin/core/target/` before starting the worker — with no enabled targets there is nothing to probe.

## Running

Two processes run independently (see [ARCHITECTURE.md](ARCHITECTURE.md)):

```powershell
# Terminal 1 — dashboard (binds to 127.0.0.1 only)
.\.venv\Scripts\python.exe manage.py runserver

# Terminal 2 — measurement worker (run elevated for full ICMP fidelity — see below)
.\.venv\Scripts\python.exe manage.py run_worker
```

Visit `http://127.0.0.1:8000/`.

## Administrator / elevation

Raw ICMP probes (used for latency/loss/jitter) and some interface statistics require the worker
process to run elevated on Windows. If `run_worker` is **not** run as Administrator:

- It prints a warning at startup and the dashboard shows a "Not running as Administrator" banner.
- ICMP probes will typically fail with a permission error and be recorded as failed measurements
  (`error` field set) rather than crashing the worker — see [DECISIONS.md](DECISIONS.md).
- All other probe types (DNS, HTTP, TCP, route, MTU, throughput, interface counters) work without
  elevation.

To run elevated: right-click PowerShell/Terminal → "Run as administrator", then re-run the
`run_worker` command from that elevated shell.

## Windows Firewall

The first time probes make outbound connections (or, if ever changed to accept inbound), Windows
may show a firewall prompt. Allow it for both Private and Public networks if prompted, otherwise
some probes (especially ICMP) may silently fail.

## Optional: start the worker automatically at logon

The worker is a manually-started console process by design (see [DECISIONS.md](DECISIONS.md) —
no Windows Service was implemented). If you want it to start automatically:

1. Create a `.bat` launcher, e.g. `run_worker.bat` in the project root:
   ```bat
   @echo off
   cd /d %~dp0
   ".venv\Scripts\pythonw.exe" manage.py run_worker
   ```
   (`pythonw.exe` avoids a visible console window; use `python.exe` instead if you want to see output.)
2. Open Task Scheduler → Create Task → Trigger: "At log on" → Action: run the `.bat` file above →
   under General, check "Run with highest privileges" if you want elevated ICMP fidelity.

This is a convenience only — closing the worker's window (or ending the scheduled task) simply
stops new measurements from being collected; nothing else in the application is affected, and it
resumes cleanly whenever it's started again.

## Testing

```powershell
.\.venv\Scripts\python.exe manage.py test
# or, equivalently:
.\.venv\Scripts\python.exe -m pytest
```

All tests mock outward network I/O (`unittest.mock`/`responses`/subprocess mocking) — the suite
never makes real network calls and does not require elevation to pass.
