/**
 * static/js/dashboard.js
 * ----------------------
 * Handles the backup form submission, progress UI,
 * result modal, and the cleanup widget.
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Elements ─────────────────────────────────────────────── */
  const form           = document.getElementById('backupForm');
  const startBtn       = document.getElementById('startBtn');
  const progressSec    = document.getElementById('progressSection');
  const progressBar    = document.getElementById('progressBar');
  const progressLabel  = document.getElementById('progressLabel');
  const progressTime   = document.getElementById('progressTime');
  const backupAlert    = document.getElementById('backupAlert');
  const resultModal    = new bootstrap.Modal('#resultModal');
  const modalTitle     = document.getElementById('modalTitle');
  const modalBody      = document.getElementById('modalBody');
  const modalHeader    = document.getElementById('modalHeader');

  /* ── Backup Form Submit ───────────────────────────────────── */
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const source      = document.getElementById('source').value.trim();
    const destination = document.getElementById('destination').value.trim();
    const compress    = document.getElementById('compress').checked;
    const incremental = document.getElementById('incremental').checked;
    const dry_run     = document.getElementById('dry_run').checked;

    // Client-side validation
    if (!source || !destination) {
      showAlert(backupAlert, 'danger', 'Please fill in both Source and Destination paths.');
      return;
    }

    // Lock UI
    startBtn.disabled = true;
    startBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>Running…`;
    hideAlert(backupAlert);
    showProgress(dry_run ? 'Simulating backup (dry run)…' : 'Starting backup…');

    // Track elapsed time
    const startTime = Date.now();
    const timer = setInterval(() => {
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      progressTime.textContent = `${elapsed}s elapsed`;
    }, 500);

    try {
      const res = await fetch('/run-backup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, destination, compress, incremental, dry_run })
      });

      const data = await res.json();
      clearInterval(timer);
      hideProgress();

      if (data.status === 'success' || data.status === 'dry_run') {
        showResult(data, true);
      } else {
        showResult(data, false);
      }

    } catch (err) {
      clearInterval(timer);
      hideProgress();
      showAlert(backupAlert, 'danger', `Network error: ${err.message}`);
    } finally {
      startBtn.disabled = false;
      startBtn.innerHTML = `<i class="bi bi-play-fill me-2"></i>Start Backup`;
    }
  });

  /* ── Show Result Modal ────────────────────────────────────── */
  function showResult(data, success) {
    const statusColor = data.status === 'dry_run' ? 'warning' :
                        success ? 'success' : 'danger';
    const icon = data.status === 'dry_run' ? 'bi-eye-fill' :
                 success ? 'bi-check-circle-fill' : 'bi-x-circle-fill';

    modalHeader.className = `modal-header bg-${statusColor}-subtle`;
    modalTitle.innerHTML = `
      <i class="bi ${icon} text-${statusColor} me-2"></i>
      ${data.status === 'dry_run' ? 'Dry Run Complete' : success ? 'Backup Successful' : 'Backup Failed'}
    `;

    const badge = (val, color, label) =>
      `<div class="text-center">
         <div class="fw-700 fs-5 text-${color}">${val}</div>
         <div class="text-muted" style="font-size:.75rem;">${label}</div>
       </div>`;

    modalBody.innerHTML = `
      <p class="mb-3 text-muted small">${data.message || ''}</p>
      <div class="d-flex justify-content-around bg-light rounded p-3 mb-3">
        ${badge(data.total_files || 0,   'primary', 'Total')}
        ${badge(data.copied_files || 0,  'success', 'Copied')}
        ${badge(data.skipped_files || 0, 'warning', 'Skipped')}
        ${badge(data.failed_files || 0,  'danger',  'Failed')}
      </div>
      <div class="d-flex gap-3 justify-content-center small text-muted">
        <span><i class="bi bi-hdd me-1"></i>${data.total_size || '0 B'}</span>
        <span><i class="bi bi-stopwatch me-1"></i>${data.duration || 0}s</span>
        ${data.zip_path ? `<span><i class="bi bi-file-zip me-1"></i>ZIP created</span>` : ''}
        ${data.is_dry_run ? `<span class="text-warning"><i class="bi bi-eye me-1"></i>Dry Run</span>` : ''}
      </div>
      ${data.backup_id ? `
        <div class="mt-3 text-center">
          <a href="/history/${data.backup_id}" class="btn btn-sm btn-outline-primary">
            <i class="bi bi-eye me-1"></i>View Details
          </a>
        </div>` : ''}
    `;

    resultModal.show();
  }

  /* ── Progress UI ──────────────────────────────────────────── */
  function showProgress(label) {
    progressLabel.textContent = label;
    progressTime.textContent = '';
    progressSec?.classList.remove('d-none');
    progressBar?.classList.add('progress-bar-animated');
  }

  function hideProgress() {
    progressSec?.classList.add('d-none');
  }

  /* ── Alert Helpers ────────────────────────────────────────── */
  function showAlert(el, type, msg) {
    if (!el) return;
    el.className = `alert alert-${type} d-flex align-items-center gap-2`;
    el.innerHTML = `<i class="bi bi-${type === 'danger' ? 'x-circle' : 'info-circle'}"></i>${msg}`;
    el.classList.remove('d-none');
  }

  function hideAlert(el) {
    el?.classList.add('d-none');
  }

  /* ── Auto Cleanup Widget ──────────────────────────────────── */
  const cleanupBtn   = document.getElementById('cleanupBtn');
  const cleanupDest  = document.getElementById('cleanupDest');
  const keepLast     = document.getElementById('keepLast');
  const cleanupAlert = document.getElementById('cleanupAlert');

  cleanupBtn?.addEventListener('click', async () => {
    const destination = cleanupDest?.value.trim();
    const keep = parseInt(keepLast?.value) || 5;

    if (!destination) {
      showAlert(cleanupAlert, 'warning', 'Please enter a destination folder path.');
      return;
    }

    if (!confirm(`Delete all but the ${keep} most recent backups in:\n${destination}\n\nThis cannot be undone.`)) {
      return;
    }

    cleanupBtn.disabled = true;
    cleanupBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span>`;

    try {
      const res = await fetch('/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ destination, keep_last: keep })
      });
      const data = await res.json();

      if (data.deleted !== undefined) {
        showAlert(cleanupAlert, 'success',
          `Deleted ${data.deleted} backup(s). Freed ${data.freed_size}.`);
      } else {
        showAlert(cleanupAlert, 'danger', data.message || 'Cleanup failed.');
      }
    } catch (err) {
      showAlert(cleanupAlert, 'danger', `Error: ${err.message}`);
    } finally {
      cleanupBtn.disabled = false;
      cleanupBtn.innerHTML = `<i class="bi bi-trash3 me-1"></i>Cleanup`;
    }
  });

});
