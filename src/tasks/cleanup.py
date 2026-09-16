"""
Database cleanup and retention management.
Prevents database from growing indefinitely by removing old raw measurements.
"""
import sqlite3
from datetime import datetime, timezone


def get_db_connection(db_path: str):
    """Get database connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cleanup_old_measurements(
    db_path: str,
    retention_days: int = 7,
    max_size_mb: int = 50000,
) -> dict:
    """
    Clean up old measurements if database is approaching size limit.

    Args:
        db_path: Path to SQLite database
        retention_days: Keep measurements for this many days
        max_size_mb: Maximum database size in MB before cleanup

    Returns:
        Cleanup statistics
    """
    import os

    # Get file size
    try:
        file_size_bytes = os.path.getsize(db_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
    except OSError:
        file_size_mb = 0

    if file_size_mb < max_size_mb:
        return {
            "cleanup_performed": False,
            "current_size_mb": round(file_size_mb, 2),
            "max_size_mb": max_size_mb,
        }

    # Get current time
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = (now_utc - __import__("datetime").timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Count before cleanup
    cursor.execute("SELECT COUNT(*) FROM measurements")
    count_before = cursor.fetchone()[0]

    # Delete old measurements (older than retention_days)
    cursor.execute("""
        DELETE FROM measurements WHERE timestamp_utc < ?
    """, (cutoff_utc,))

    conn.commit()

    # Get deletion count
    rows_deleted = cursor.rowcount
    cursor.execute("SELECT COUNT(*) FROM measurements")
    count_after = cursor.fetchone()[0]

    conn.close()

    return {
        "cleanup_performed": True,
        "timestamp_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retention_days": retention_days,
        "rows_deleted": rows_deleted,
        "measurement_count_before": count_before,
        "measurement_count_after": count_after,
        "current_size_mb": round(file_size_mb, 2),
        "max_size_mb": max_size_mb,
    }


def get_database_statistics(
    db_path: str,
) -> dict:
    """Get database statistics."""
    import os

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Table sizes
    tables = ["measurements", "outages", "sla_events", "events"]
    stats = {}

    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]

            cursor.execute(f"SELECT SUM(LENGTH(sql)) FROM sqlite_master WHERE type='table' AND name=?", (table,))
            result = cursor.fetchone()
            table_size = result[0] if result and result[0] else 0

            stats[table] = {
                "row_count": row_count,
                "size_bytes": table_size,
                "exists": True,
            }
        except Exception as e:
            stats[table] = {"error": str(e)}

    # Overall database size
    try:
        file_size_mb = os.path.getsize(db_path) / (1024 * 1024)
        stats["total_size_mb"] = round(file_size_mb, 2)
    except OSError:
        stats["total_size_mb"] = None

    conn.close()
    return stats


def optimize_database(db_path: str) -> dict:
    """Run database optimization (VACUUM for SQLite)."""
    import sqlite3

    try:
        conn = get_db_connection(db_path)
        cursor = conn.cursor()

        # SQLite doesn't automatically optimize, but VACUUM can reclaim space
        cursor.execute("VACUUM")
        conn.commit()

        return {
            "optimized": True,
            "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    except Exception as e:
        return {
            "optimized": False,
            "error": str(e),
        }
