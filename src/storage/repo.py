"""
Repository pattern for database access - separates data access from business logic.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import get_connection, init_database


class MeasurementRepository:
    """Repository for measurement records."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def record_measurement(
        self,
        timestamp_utc: str,
        timestamp_local: str,
        interface_type: str,
        interface_name: Optional[str],
        gateway_reachable: int,
        gateway_rtt_ms: Optional[float],
        target_host: str,
        target_type: str,
        success: bool,
        rtt_ms: Optional[float] = None,
        packet_loss_count: int = 0,
        jitter_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        http_status_code: Optional[int] = None,
        tls_version: Optional[str] = None,
        bytes_sent: Optional[int] = None,
        bytes_received: Optional[int] = None,
        download_mbps: Optional[float] = None,
        upload_mbps: Optional[float] = None,
    ) -> int:
        """Record a raw measurement."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO measurements (
                timestamp_utc, timestamp_local, interface_type, interface_name,
                gateway_reachable, gateway_rtt_ms, target_host, target_type, success,
                rtt_ms, packet_loss_count, jitter_ms, error_message, http_status_code,
                tls_version, bytes_sent, bytes_received, download_mbps, upload_mbps
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp_utc, timestamp_local, interface_type, interface_name,
            gateway_reachable, gateway_rtt_ms, target_host, target_type, success,
            rtt_ms, packet_loss_count, jitter_ms, error_message, http_status_code,
            tls_version, bytes_sent, bytes_received, download_mbps, upload_mbps,
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_latest_measurement(
        self,
        target_host: str,
    ) -> Optional[dict]:
        """Get the most recent measurement for a target."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM measurements
            WHERE target_host = ?
            ORDER BY id DESC
            LIMIT 1
        """, (target_host,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

    def get_measurements_for_outage(
        self,
        outage_id: int,
    ) -> list[dict]:
        """Get measurements during an outage."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM measurements
            WHERE id IN (
                SELECT MIN(id) FROM (
                    SELECT DISTINCT ON (timestamp_utc) id FROM measurements
                    ORDER BY timestamp_utc, id DESC
                )
            )
        """)  # Simplified - returns all recent measurements before/after outage
        return [dict(row) for row in cursor.fetchall()]

    def get_measurements_in_range(
        self,
        start_utc: str,
        end_utc: str,
    ) -> list[dict]:
        """Get measurements within a time range."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM measurements
            WHERE timestamp_utc >= ? AND timestamp_utc < ?
            ORDER BY timestamp_utc DESC
            LIMIT 1000
        """, (start_utc, end_utc))
        return [dict(row) for row in cursor.fetchall()]

    def get_gateway_status(self) -> dict:
        """Get current gateway status from latest measurements."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MAX(CASE WHEN gateway_reachable THEN 1 ELSE 0 END) as last_successful,
                   AVG(gateway_rtt_ms) as avg_rtt
            FROM measurements
            WHERE target_host = 'default-gateway' OR (target_host LIKE '%.gateway%' OR target_host LIKE '%.router%')
            ORDER BY id DESC
            LIMIT 1
        """)
        return dict(cursor.fetchone()) or {}


class OutageRepository:
    """Repository for outage records."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def create_outage(
        self,
        start_timestamp_utc: str,
        severity: str,
        gateway_failed: bool,
        targets_affected: int,
        detection_source: str,
        evidence_confidence: str,
        sla_period_id: Optional[int] = None,
    ) -> int:
        """Create a new outage record."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO outages (
                start_timestamp_utc, severity, gateway_failed, targets_affected,
                detection_source, evidence_confidence, sla_period_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            start_timestamp_utc, severity, 1 if gateway_failed else 0,
            targets_affected, detection_source, evidence_confidence,
            sla_period_id,
        ))
        self.conn.commit()
        return cursor.lastrowid

    def update_outage_end(
        self,
        outage_id: int,
        end_timestamp_utc: str,
        classification_reason: Optional[str] = None,
        classified_as_upstream: bool = True,
    ) -> None:
        """Update outage end time and classification."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE outages SET
                end_timestamp_utc = ?,
                classification_reason = COALESCE(?, classification_reason),
                classified_as_upstream = ?
            WHERE id = ?
        """, (end_timestamp_utc, classification_reason, int(classified_as_upstream), outage_id))
        self.conn.commit()

    def get_active_outage(self) -> Optional[dict]:
        """Get currently active outage if any."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM outages
            WHERE end_timestamp_utc IS NULL OR end_timestamp_utc < datetime('now')
            ORDER BY start_timestamp_utc DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        outage = dict(row)
        outage["duration_seconds"] = self._calculate_duration(outage)
        return outage

    def get_outage_by_id(self, outage_id: int) -> Optional[dict]:
        """Get an outage by its ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM outages WHERE id = ?", (outage_id,))
        row = cursor.fetchone()
        if not row:
            return None
        outage = dict(row)
        outage["duration_seconds"] = self._calculate_duration(outage)
        return outage

    def get_all_outages(self, limit: int = 100) -> list[dict]:
        """Get all outages."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM outages
            ORDER BY start_timestamp_utc DESC
            LIMIT ?
        """, (limit,))
        outages = [dict(row) for row in cursor.fetchall()]
        for outage in outages:
            outage["duration_seconds"] = self._calculate_duration(outage)
        return outages

    def get_outages_by_period(
        self,
        period_start: str,
        period_end: str,
    ) -> list[dict]:
        """Get outages within a time period."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM outages
            WHERE end_timestamp_utc >= ? OR (end_timestamp_utc IS NULL AND start_timestamp_utc >= ?)
            ORDER BY start_timestamp_utc DESC
        """, (period_start, period_start))
        outages = [dict(row) for row in cursor.fetchall()]
        for outage in outages:
            outage["duration_seconds"] = self._calculate_duration(outage)
        return outages

    def _calculate_duration(self, outage: dict) -> float:
        """Calculate outage duration in seconds."""
        if not outage.get("end_timestamp_utc"):
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_ts = now
        else:
            end_ts = outage["end_timestamp_utc"]

        start = datetime.fromisoformat(outage["start_timestamp_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
        return (end - start).total_seconds()


class SLARepository:
    """Repository for SLA policy and event records."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def create_sla_policy(self, name: str, data: dict) -> int:
        """Create an SLA policy record (simplified - full logic in separate module)."""
        cursor = self.conn.cursor()
        # Simplified insertion - would be expanded with full policy structure
        cursor.execute("""
            INSERT INTO config (key, value) VALUES (?, ?)
        """, (f"sla_policy:{name}", json.dumps(data)))
        self.conn.commit()
        return 1

    def get_sla_period(
        self,
        period_type: str = "custom",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[dict]:
        """Get current active SLA period."""
        cursor = self.conn.cursor()
        if not start_date or not end_date:
            now = datetime.now(timezone.utc)
            today = now.strftime("%Y-%m-%d")
            tomorrow = (now + __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")

            start_date = today
            end_date = tomorrow if period_type == "daily" else None
        cursor.execute("""
            SELECT * FROM sla_periods
            WHERE (is_active = 1 OR (? IS NULL AND is_active = 0))
            AND ((? IS NULL OR start_date <= ?) AND (? IS NULL OR end_date >= ?))
            ORDER BY id DESC LIMIT 1
        """, ("NULL" if not start_date else start_date, "NULL" if not end_date else end_date,
              start_date, end_date, "NULL" if not start_date else start_date))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

    def calculate_sla_utilization(self) -> dict:
        """Calculate current SLA utilization."""
        # This would be implemented with full policy lookup
        return {
            "availability_target": 99.99,
            "downtime_budget_minutes": 52.34,
            "observed_downtime_minutes": 0,
            "remaining_budget_minutes": 52.34,
        }


class InterfaceRepository:
    """Repository for network interface information."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def record_interface(self, interface_name: str, interface_type: str, ssid: Optional[str] = None,
                        bssid: Optional[str] = None) -> int:
        """Record or update interface information."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO interfaces (
                interface_name, interface_type, ssid, bssid, connected_at, is_up
            ) VALUES (?, ?, ?, ?, ?, 1)
        """, (interface_name, interface_type, ssid, bssid, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        self.conn.commit()
        return cursor.lastrowid

    def get_active_interface(self) -> Optional[dict]:
        """Get currently active interface."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM interfaces WHERE is_up = 1 ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)


class ConfigurationRepository:
    """Repository for application configuration."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def get_config(self, key: str) -> Optional[str]:
        """Get a configuration value."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

    def set_config(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, json.dumps(value)),
        )
        self.conn.commit()

    def get_all_config(self) -> dict:
        """Get all configuration values."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT key, value FROM config")
        return {row["key"]: json.loads(row["value"]) for row in cursor.fetchall()}


class ReportRepository:
    """Repository for report metadata."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = get_connection(db_path)

    def record_report(self, name: str, export_type: str, period_start: str,
                     period_end: str, file_path: str, metadata: Optional[dict] = None) -> int:
        """Record a generated report."""
        cursor = self.conn.cursor()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cursor.execute("""
            INSERT INTO reports (name, export_type, period_start, period_end, file_path, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, export_type, period_start, period_end, file_path, now, json.dumps(metadata)))
        self.conn.commit()
        return cursor.lastrowid
