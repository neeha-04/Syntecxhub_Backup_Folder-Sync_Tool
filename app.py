"""
app.py
------
Main Flask application entry point for the Folder Backup & Sync Tool.
Defines all routes and wires together the service and database layers.
"""
import webbrowser
import os
import json
from flask import (
    Flask, render_template, request,
    jsonify, send_file, redirect, url_for, flash
)
from datetime import datetime

from database.db_manager import (
    init_db, get_all_backups, get_backup_by_id,
    get_logs_for_backup, get_statistics
)
from services.backup_service import (
    run_backup, restore_backup,
    cleanup_old_backups, delete_backup_files
)

# ── App Initialization ─────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "backup_tool_secret_key_2024"  # Required for flash messages

# Initialize database on startup
init_db()


# ── Template Helpers ───────────────────────────────────────────────────────────

@app.template_filter("filesize")
def filesize_filter(size_bytes):
    """Jinja2 filter: Convert bytes to human-readable size."""
    if not size_bytes:
        return "0 B"
    size_bytes = int(size_bytes)
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


@app.template_filter("datefmt")
def datefmt_filter(iso_str):
    """Jinja2 filter: Format ISO datetime string nicely."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y %H:%M:%S")
    except Exception:
        return iso_str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """
    Dashboard home page.
    Shows statistics summary and the backup configuration form.
    """
    stats = get_statistics()
    recent_backups = get_all_backups()[:5]  # Last 5 for quick view
    return render_template("index.html", stats=stats, recent_backups=recent_backups)


@app.route("/run-backup", methods=["POST"])
def trigger_backup():
    """
    Handle POST from the backup form.
    Reads form fields, calls the backup service, and returns JSON result.
    """
    data = request.get_json() or request.form

    source = data.get("source", "").strip()
    destination = data.get("destination", "").strip()
    compress = str(data.get("compress", "true")).lower() == "true"
    incremental = str(data.get("incremental", "false")).lower() == "true"
    dry_run = str(data.get("dry_run", "false")).lower() == "true"

    # Basic validation
    if not source or not destination:
        return jsonify({"status": "error", "message": "Source and destination are required."}), 400

    # Run the backup
    result = run_backup(
        source=source,
        destination=destination,
        compress=compress,
        incremental=incremental,
        dry_run=dry_run
    )

    return jsonify(result)


@app.route("/history")
def history():
    """
    Full backup history page.
    Shows a table of all backup jobs.
    """
    backups = get_all_backups()
    return render_template("history.html", backups=backups)


@app.route("/history/<int:backup_id>")
def backup_detail(backup_id):
    """
    Detail page for a single backup job.
    Shows per-file log entries.
    """
    backup = get_backup_by_id(backup_id)
    if not backup:
        flash("Backup record not found.", "danger")
        return redirect(url_for("history"))

    logs = get_logs_for_backup(backup_id)
    return render_template("detail.html", backup=backup, logs=logs)


@app.route("/download/<int:backup_id>")
def download_backup(backup_id):
    """
    Stream a ZIP backup file for download.
    """
    backup = get_backup_by_id(backup_id)
    if not backup:
        return jsonify({"error": "Backup not found"}), 404

    zip_path = backup.get("zip_path")
    if not zip_path or not os.path.isfile(zip_path):
        flash("ZIP file not found on disk.", "warning")
        return redirect(url_for("history"))

    return send_file(
        zip_path,
        as_attachment=True,
        download_name=os.path.basename(zip_path)
    )


@app.route("/delete/<int:backup_id>", methods=["POST"])
def delete_backup(backup_id):
    """
    Delete a backup record and its files from disk.
    """
    backup = get_backup_by_id(backup_id)
    if not backup:
        return jsonify({"status": "error", "message": "Backup not found"}), 404

    result = delete_backup_files(backup)
    return jsonify(result)


@app.route("/restore", methods=["POST"])
def restore():
    """
    Restore a ZIP backup to a target directory.
    Accepts JSON: { backup_id, restore_path }
    """
    data = request.get_json() or {}
    backup_id = data.get("backup_id")
    restore_path = data.get("restore_path", "").strip()

    if not backup_id or not restore_path:
        return jsonify({"status": "error", "message": "backup_id and restore_path are required."}), 400

    backup = get_backup_by_id(backup_id)
    if not backup:
        return jsonify({"status": "error", "message": "Backup record not found."}), 404

    zip_path = backup.get("zip_path")
    if not zip_path or not os.path.isfile(zip_path):
        return jsonify({"status": "error", "message": "ZIP file not found on disk."}), 404

    result = restore_backup(zip_path, restore_path)
    return jsonify(result)


@app.route("/cleanup", methods=["POST"])
def cleanup():
    """
    Delete old backups from a destination folder, keeping the N most recent.
    Accepts JSON: { destination, keep_last }
    """
    data = request.get_json() or {}
    destination = data.get("destination", "").strip()
    keep_last = int(data.get("keep_last", 5))

    if not destination:
        return jsonify({"status": "error", "message": "Destination path required."}), 400

    result = cleanup_old_backups(destination, keep_last)
    return jsonify(result)


@app.route("/api/stats")
def api_stats():
    """API endpoint: Return dashboard statistics as JSON."""
    return jsonify(get_statistics())


@app.route("/api/backups")
def api_backups():
    """API endpoint: Return all backups as JSON."""
    return jsonify(get_all_backups())


# ── Error Handlers ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("404.html", error=str(e)), 500


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("   Folder Backup & Sync Tool")
    print("   Running at: http://127.0.0.1:5000")
    print("=" * 55 + "\n")
    webbrowser.open("http://127.0.0.1:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)
