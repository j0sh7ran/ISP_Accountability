"""
SQLite models and schema for ISP Accountability monitoring application.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_path: str) -> None:
    """Initialize all tables in the database."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON")

    # Measurements table - raw probe results
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_utc TEXT NOT NULL,
            timestamp_local TEXT NOT NULL,
            interface_type TEXT NOT NULL,
            interface_name TEXT,
            gateway_reachable INTEGER,
            gateway_rtt_ms REAL,
            target_host TEXT NOT NULL,
            target_type TEXT NOT NULL,  -- icmp, dns, tcp, https
            success INTEGER,
            rtt_ms REAL,
            packet_loss_count INTEGER DEFAULT 0,
            jitter_ms REAL,
            error_message TEXT,
            http_status_code INTEGER,
            tls_version TEXT,
            bytes_sent INTEGER,
            bytes_received INTEGER,
            download_mbps REAL,
            upload_mbps REAL,
            FOREIGN KEY (target_host) REFERENCES targets(id)
        )
    """)

    # Outages table - detected connectivity incidents
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_timestamp_utc TEXT NOT NULL,
            end_timestamp_utc TEXT,
            duration_seconds REAL,
            severity TEXT NOT NULL,  -- minor, moderate, severe, critical
            gateway_failed INTEGER DEFAULT 0,
            targets_affected INTEGER DEFAULT 0,
            detection_source TEXT,  -- auto, manual, simulation
            evidence_confidence TEXT NOT NULL,  -- local-only, likely-upstream, probable-upstream, upstream-confirmed, endpoint-specific
            classified_as_upstream INTEGER DEFAULT 0,
            classification_reason TEXT,
            sla_period_id INTEGER,
            FOREIGN KEY (sla_period_id) REFERENCES sla_periods(id)
        )
    """)

    # SLA events table - events evaluated against policy
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sla_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outage_id INTEGER NOT NULL,
            start_timestamp_utc TEXT NOT NULL,
            end_timestamp_utc TEXT,
            duration_seconds REAL NOT NULL,
            status TEXT NOT NULL,  -- pending, excluded, confirmed, disputed
            exclusion_reason TEXT,
            policy_name TEXT NOT NULL,
            policy_period_start TEXT,
            policy_period_end TEXT,
            FOREIGN KEY (outage_id) REFERENCES outages(id),
            UNIQUE(outage_id, policy_name)
        )
    """)

    # SLA periods table - configurable time periods for SLA calculation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sla_periods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            period_type TEXT NOT NULL,  -- daily, monthly, custom
            availability_target REAL,
            max_outage_duration_seconds REAL,
            response_time_seconds REAL,
            restoration_time_seconds REAL,
            is_active INTEGER DEFAULT 0
        )
    """)

    # Maintenance windows table - planned maintenance exclusions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_timestamp TEXT,
            scheduled_start TEXT NOT NULL,
            scheduled_end TEXT NOT NULL,
            actual_start TEXT,
            actual_end TEXT,
            scope TEXT,
            is_service_interruption_expected INTEGER DEFAULT 1,
            notification_lead_hours REAL,
            maintenance_window_hours REAL,
            excluded_from_sla INTEGER DEFAULT 1
        )
    """)

    # Targets table - configurable endpoints to probe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            target_type TEXT NOT NULL,  -- icmp, dns, tcp, https
            port INTEGER DEFAULT 0,
            expected_http_status INTEGER,
            description TEXT,
            weight REAL DEFAULT 1.0,  -- influence on upstream determination
            is_active INTEGER DEFAULT 1,
            UNIQUE(host)
        )
    """)

    # Support tickets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT NOT NULL,
            isp_provider TEXT,
            contact_method TEXT,  -- email, phone, webform, app
            date_opened TEXT NOT NULL,
            date_closed TEXT,
            representative_name TEXT,
            incident_id TEXT,
            cause_description TEXT,
            outage_duration_minutes REAL,
            service_credit_offered TEXT,
            corrective_action TEXT,
            UNIQUE(ticket_number)
        )
    """)

    # Annotations table - manual notes and classifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,  -- outage, measurement, event
            entity_id INTEGER NOT NULL,
            annotation_type TEXT NOT NULL,  -- note, classification, symptom_report, work_impact
            author TEXT NOT NULL,
            created_timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            is_confidential INTEGER DEFAULT 0
        )
    """)

    # Interface information table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interfaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interface_name TEXT NOT NULL,
            interface_type TEXT NOT NULL,  -- wifi, ethernet, cellular
            ssid TEXT,
            bssid TEXT,
            mac_address TEXT,
            link_speed_mbps REAL,
            is_up INTEGER DEFAULT 1,
            connected_at TEXT,
            UNIQUE(interface_name)
        )
    """)

    # Configuration table - application settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Reports table - generated report metadata
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            export_type TEXT NOT NULL,  -- pdf, csv, json, html
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            status TEXT NOT NULL,  -- pending, generated, error
            file_path TEXT,
            created_at TEXT NOT NULL,
            metadata TEXT
        )
    """)

    # Events table - all measured events (for SLA classification)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measurement_id INTEGER NOT NULL,
            outage_id INTEGER,
            start_timestamp_utc TEXT NOT NULL,
            end_timestamp_utc TEXT,
            duration_seconds REAL DEFAULT 0,
            event_type TEXT NOT NULL,  -- connection_lost, degraded, recovered
            severity TEXT,
            raw_data JSON,
            classification TEXT,  -- local, upstream, endpoint-specific, unknown
            is_confidential INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def seed_default_targets(db_path: str) -> None:
    """Seed default target endpoints if not already present."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    default_targets = [
        ("1.1.1.1", "icmp", 0, 2026-09-16, "Cloudflare DNS (primary)"),
        ("8.8.8.8", "icmp", 0, 2026-09-16, "Google Public DNS"),
        ("9.9.9.9", "icmp", 0, 2026-09-16, "Quad9 DNS"),
        ("cloudflare-dns.com", "dns", 0, 2026-09-16, "Cloudflare DNS over HTTPS"),
        ("8.8.8.8", "dns", 0, 2026-09-16, "Google Public DNS"),
        ("1.1.1.1", "tcp", 443, 2026-09-16, "Cloudflare HTTPS endpoint"),
        ("8.8.8.8", "tcp", 443, 2026-09-16, "Google Public DNS over HTTPS"),
    ]

    cursor.execute("""
        INSERT OR IGNORE INTO targets (host, target_type, port, created_at, description)
        VALUES (?, ?, ?, ?, ?)
    """)

    for host, target_type, port, created_at, description in default_targets:
        try:
            cursor.execute(
                "INSERT INTO targets (host, target_type, port, created_at, description) VALUES (?, ?, ?, ?, ?)",
                (host, target_type, port, created_at, description)
            )
        except sqlite3.IntegrityError:
            # Target already exists
            pass

    conn.commit()
    conn.close()
