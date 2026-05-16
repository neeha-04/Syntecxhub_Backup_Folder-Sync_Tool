"""
database/db_manager.py
----------------------
Handles all SQLite database operations for the Folder Backup Tool.
Stores backup history, logs, and statistics.
"""

import sqlite3
import os
from datetime import datetime

# Path to the SQLite database file
DB_PATH = os.path.join(os.path.dirname(__file__), "backup_history.db")


def get_connection():
    """Create and return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allows dict-like row access
    return conn


def init_db():
    """
    Initialize the database by creating tables if they don't exist.
    Called once when the Flask app starts.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Table to store each backup job
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backup_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            dest_path TEXT NOT NULL,
            backup_name TEXT NOT NULL,
            backup_type TEXT DEFAULT 'full',       -- 'full' or 'incremental'
            status TEXT DEFAULT 'pending',          -- 'pending', 'success', 'failed', 'dry_run'
            is_zip INTEGER DEFAULT 0,               -- 1 if ZIP compressed
            total_files INTEGER DEFAULT 0,
            copied_files INTEGER DEFAULT 0,
            skipped_files INTEGER DEFAULT 0,
            failed_files INTEGER DEFAULT 0,
            total_size_bytes INTEGER DEFAULT 0,
            zip_path TEXT,                          -- Path to ZIP file if compressed
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL DEFAULT 0
        )
    """)

    # Table to store per-file log entries for each backup
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backup_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            action TEXT NOT NULL,    -- 'copied', 'skipped', 'failed', 'deleted'
            reason TEXT,
            timestamp TEXT,
            FOREIGN KEY (backup_id) REFERENCES backup_history(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")


def create_backup_record(source, dest, backup_name, backup_type, is_zip):
    """
    Insert a new backup record and return its ID.
    Called at the start of a backup job.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO backup_history
            (source_path, dest_path, backup_name, backup_type, status, is_zip, started_at)
        VALUES (?, ?, ?, ?, 'pending', ?, ?)
    """, (source, dest, backup_name, backup_type, 1 if is_zip else 0,
          datetime.now().isoformat()))
    conn.commit()
    backup_id = cursor.lastrowid
    conn.close()
    return backup_id


def update_backup_record(backup_id, **kwargs):
    """
    Update an existing backup record with arbitrary fields.
    Accepts keyword arguments matching column names.
    """
    if not kwargs:
        return

    conn = get_connection()
    cursor = conn.cursor()

    # Dynamically build SET clause
    set_clause = ", ".join([f"{k} = ?" for k in kwargs])
    values = list(kwargs.values()) + [backup_id]

    cursor.execute(f"UPDATE backup_history SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def add_log_entry(backup_id, file_path, action, reason=None):
    """
    Add a per-file log entry linked to a backup job.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO backup_logs (backup_id, file_path, action, reason, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (backup_id, file_path, action, reason, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_all_backups():
    """
    Retrieve all backup records ordered by most recent first.
    Returns a list of dict-like Row objects.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM backup_history ORDER BY id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_backup_by_id(backup_id):
    """Retrieve a single backup record by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM backup_history WHERE id = ?", (backup_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_logs_for_backup(backup_id):
    """Retrieve all log entries for a specific backup job."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM backup_logs WHERE backup_id = ? ORDER BY id ASC
    """, (backup_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_backup_record(backup_id):
    """
    Delete a backup record and all its associated logs.
    Note: Does NOT delete the actual backup files from disk.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM backup_logs WHERE backup_id = ?", (backup_id,))
    cursor.execute("DELETE FROM backup_history WHERE id = ?", (backup_id,))
    conn.commit()
    conn.close()


def get_statistics():
    """
    Return aggregate statistics across all backup jobs.
    Used for the dashboard summary cards.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total_backups,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'dry_run' THEN 1 ELSE 0 END) as dry_runs,
            SUM(total_files) as total_files_processed,
            SUM(total_size_bytes) as total_bytes_backed_up
        FROM backup_history
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}
