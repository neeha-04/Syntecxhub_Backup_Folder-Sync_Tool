"""
services/backup_service.py
--------------------------
Core backup engine. Handles:
  - Full and incremental backups
  - ZIP compression
  - File diff detection (MD5 hash comparison)
  - Dry-run mode
  - Logging to DB and text log file
  - Restore from backup
  - Auto cleanup of old backups
"""

import os
import shutil
import hashlib
import zipfile
import logging
from datetime import datetime

from database.db_manager import (
    create_backup_record, update_backup_record,
    add_log_entry, delete_backup_record
)

# ── Logging Setup ──────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "backup.log")),
    ]
)
logger = logging.getLogger(__name__)


# ── Helper Utilities ───────────────────────────────────────────────────────────

def _get_file_hash(filepath: str) -> str:
    """
    Compute MD5 hash of a file for change detection.
    Used in incremental backups to skip unchanged files.
    """
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (IOError, OSError):
        return ""


def _format_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def _get_folder_size(folder_path: str) -> int:
    """Recursively calculate total size of all files in a folder."""
    total = 0
    for dirpath, _, filenames in os.walk(folder_path):
        for fname in filenames:
            fp = os.path.join(dirpath, fname)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def _build_file_index(folder_path: str) -> dict:
    """
    Walk a folder and return a dict: {relative_path: md5_hash}.
    Used to detect which files changed since the last backup.
    """
    index = {}
    for dirpath, _, filenames in os.walk(folder_path):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, folder_path)
            index[rel_path] = _get_file_hash(full_path)
    return index


def _zip_folder(folder_path: str, zip_path: str) -> bool:
    """
    Compress an entire folder into a ZIP archive.
    Returns True on success, False on failure.
    """
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for dirpath, _, filenames in os.walk(folder_path):
                for fname in filenames:
                    full_path = os.path.join(dirpath, fname)
                    arcname = os.path.relpath(full_path, os.path.dirname(folder_path))
                    zf.write(full_path, arcname)
        logger.info(f"[ZIP] Created: {zip_path}")
        return True
    except Exception as e:
        logger.error(f"[ZIP] Failed to create ZIP: {e}")
        return False


# ── Main Backup Function ───────────────────────────────────────────────────────

def run_backup(source: str, destination: str,
               compress: bool = True,
               incremental: bool = False,
               dry_run: bool = False) -> dict:
    """
    Execute a backup job.

    Parameters:
        source       : Absolute path to the source folder.
        destination  : Absolute path to the backup destination folder.
        compress     : If True, compress the backup folder into a ZIP.
        incremental  : If True, only copy files that changed since last backup.
        dry_run      : If True, simulate the backup without copying anything.

    Returns:
        A result dict with status, stats, and any error message.
    """

    # ── Validation ─────────────────────────────────────────────────────────────
    result = {
        "status": "failed",
        "backup_id": None,
        "backup_name": None,
        "message": "",
        "total_files": 0,
        "copied_files": 0,
        "skipped_files": 0,
        "failed_files": 0,
        "total_size": "0 B",
        "duration": 0,
        "zip_path": None,
        "is_dry_run": dry_run,
    }

    if not os.path.isdir(source):
        result["message"] = f"Source folder does not exist: {source}"
        logger.error(result["message"])
        return result

    if not destination:
        result["message"] = "Destination path cannot be empty."
        return result

    # Prevent backing up into itself
    if os.path.abspath(source) == os.path.abspath(destination):
        result["message"] = "Source and destination cannot be the same folder."
        return result

    # ── Setup ──────────────────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    if dry_run:
        backup_name = f"dryrun_{timestamp}"

    backup_type = "incremental" if incremental else "full"
    backup_dest_path = os.path.join(destination, backup_name)

    logger.info(f"[BACKUP] Starting {backup_type} backup | Source: {source} -> Dest: {backup_dest_path}")
    if dry_run:
        logger.info("[BACKUP] DRY-RUN mode enabled — no files will be copied.")

    start_time = datetime.now()

    # Create DB record
    backup_id = create_backup_record(
        source=source,
        dest=destination,
        backup_name=backup_name,
        backup_type=backup_type,
        is_zip=compress
    )
    result["backup_id"] = backup_id
    result["backup_name"] = backup_name

    # ── Gather Files ───────────────────────────────────────────────────────────
    source_index = _build_file_index(source)
    prev_index = {}

    # For incremental: load the previous backup's file hashes if available
    if incremental:
        prev_backup_folder = _find_last_backup_folder(destination)
        if prev_backup_folder:
            prev_index = _build_file_index(prev_backup_folder)
            logger.info(f"[INCREMENTAL] Comparing against: {prev_backup_folder}")
        else:
            logger.info("[INCREMENTAL] No previous backup found. Performing full backup.")

    total_files = len(source_index)
    copied = skipped = failed = 0
    total_bytes = 0

    # ── Copy Files ─────────────────────────────────────────────────────────────
    for rel_path, src_hash in source_index.items():
        src_file = os.path.join(source, rel_path)
        dst_file = os.path.join(backup_dest_path, rel_path)

        # Incremental: skip file if hash matches previous backup
        if incremental and rel_path in prev_index and prev_index[rel_path] == src_hash:
            skipped += 1
            logger.debug(f"[SKIP] Unchanged: {rel_path}")
            if not dry_run:
                add_log_entry(backup_id, rel_path, "skipped", "unchanged")
            continue

        if dry_run:
            # Just simulate — log what would happen
            logger.info(f"[DRY-RUN] Would copy: {rel_path}")
            copied += 1
            try:
                total_bytes += os.path.getsize(src_file)
            except OSError:
                pass
            continue

        # Actual copy
        try:
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            shutil.copy2(src_file, dst_file)  # copy2 preserves metadata
            copied += 1
            total_bytes += os.path.getsize(dst_file)
            logger.debug(f"[COPIED] {rel_path}")
            add_log_entry(backup_id, rel_path, "copied")
        except Exception as e:
            failed += 1
            logger.error(f"[FAILED] {rel_path} — {e}")
            add_log_entry(backup_id, rel_path, "failed", str(e))

    # ── ZIP Compression ────────────────────────────────────────────────────────
    zip_path = None
    if compress and not dry_run and copied > 0:
        zip_path = backup_dest_path + ".zip"
        if _zip_folder(backup_dest_path, zip_path):
            # Remove the uncompressed folder after successful zip
            shutil.rmtree(backup_dest_path, ignore_errors=True)
            logger.info(f"[ZIP] Removed uncompressed folder: {backup_dest_path}")
        else:
            zip_path = None

    # ── Finalize ───────────────────────────────────────────────────────────────
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    final_status = "dry_run" if dry_run else ("success" if failed == 0 else "failed")

    update_backup_record(
        backup_id,
        status=final_status,
        total_files=total_files,
        copied_files=copied,
        skipped_files=skipped,
        failed_files=failed,
        total_size_bytes=total_bytes,
        zip_path=zip_path,
        completed_at=end_time.isoformat(),
        duration_seconds=round(duration, 2)
    )

    result.update({
        "status": final_status,
        "total_files": total_files,
        "copied_files": copied,
        "skipped_files": skipped,
        "failed_files": failed,
        "total_size": _format_size(total_bytes),
        "duration": round(duration, 2),
        "zip_path": zip_path,
        "message": f"Backup {final_status}. {copied} files copied, {skipped} skipped, {failed} failed."
    })

    logger.info(f"[BACKUP] Completed in {duration:.2f}s — {result['message']}")
    return result


# ── Helper: Find Last Backup Folder ───────────────────────────────────────────

def _find_last_backup_folder(destination: str) -> str | None:
    """
    Scan the destination for the most recent backup folder (non-zip).
    Used for incremental backup comparison.
    """
    if not os.path.isdir(destination):
        return None

    folders = sorted([
        os.path.join(destination, d)
        for d in os.listdir(destination)
        if d.startswith("backup_") and os.path.isdir(os.path.join(destination, d))
    ], reverse=True)

    return folders[0] if folders else None


# ── Restore Function ───────────────────────────────────────────────────────────

def restore_backup(zip_path: str, restore_destination: str) -> dict:
    """
    Restore files from a ZIP backup to a target folder.

    Parameters:
        zip_path            : Path to the .zip backup file.
        restore_destination : Folder where files will be restored.

    Returns:
        A result dict with status and message.
    """
    result = {"status": "failed", "message": ""}

    if not os.path.isfile(zip_path):
        result["message"] = f"ZIP file not found: {zip_path}"
        return result

    if not zipfile.is_zipfile(zip_path):
        result["message"] = f"Not a valid ZIP file: {zip_path}"
        return result

    try:
        os.makedirs(restore_destination, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(restore_destination)
        result["status"] = "success"
        result["message"] = f"Restored to: {restore_destination}"
        logger.info(f"[RESTORE] Extracted {zip_path} -> {restore_destination}")
    except Exception as e:
        result["message"] = str(e)
        logger.error(f"[RESTORE] Failed: {e}")

    return result


# ── Cleanup Function ───────────────────────────────────────────────────────────

def cleanup_old_backups(destination: str, keep_last: int = 5) -> dict:
    """
    Delete old backup ZIP files from the destination, keeping only the N most recent.

    Parameters:
        destination : The backup destination folder.
        keep_last   : Number of recent backups to keep.

    Returns:
        A result dict with deleted count and freed space.
    """
    result = {"deleted": 0, "freed_bytes": 0, "freed_size": "0 B", "errors": []}

    if not os.path.isdir(destination):
        return result

    # Find all ZIP backups sorted oldest-first
    zips = sorted([
        os.path.join(destination, f)
        for f in os.listdir(destination)
        if f.endswith(".zip") and f.startswith("backup_")
    ])

    to_delete = zips[:-keep_last] if len(zips) > keep_last else []

    for zip_file in to_delete:
        try:
            size = os.path.getsize(zip_file)
            os.remove(zip_file)
            result["deleted"] += 1
            result["freed_bytes"] += size
            logger.info(f"[CLEANUP] Deleted: {zip_file}")
        except Exception as e:
            result["errors"].append(str(e))
            logger.error(f"[CLEANUP] Error deleting {zip_file}: {e}")

    result["freed_size"] = _format_size(result["freed_bytes"])
    return result


# ── Delete Single Backup ───────────────────────────────────────────────────────

def delete_backup_files(backup_record: dict) -> dict:
    """
    Delete the physical backup files (ZIP or folder) for a given backup record.
    Also removes the DB record.

    Parameters:
        backup_record : A dict from get_backup_by_id().

    Returns:
        Result dict with status and message.
    """
    result = {"status": "failed", "message": ""}

    backup_id = backup_record.get("id")
    zip_path = backup_record.get("zip_path")
    backup_name = backup_record.get("backup_name")
    dest = backup_record.get("dest_path")

    deleted_something = False

    # Delete ZIP file if it exists
    if zip_path and os.path.isfile(zip_path):
        try:
            os.remove(zip_path)
            deleted_something = True
            logger.info(f"[DELETE] Removed ZIP: {zip_path}")
        except Exception as e:
            result["message"] = f"Failed to delete ZIP: {e}"
            return result

    # Delete backup folder if it exists
    folder_path = os.path.join(dest, backup_name) if dest and backup_name else None
    if folder_path and os.path.isdir(folder_path):
        try:
            shutil.rmtree(folder_path)
            deleted_something = True
            logger.info(f"[DELETE] Removed folder: {folder_path}")
        except Exception as e:
            result["message"] = f"Failed to delete folder: {e}"
            return result

    # Remove DB record
    delete_backup_record(backup_id)

    result["status"] = "success"
    result["message"] = "Backup deleted successfully." if deleted_something else "DB record removed (no files found)."
    return result
