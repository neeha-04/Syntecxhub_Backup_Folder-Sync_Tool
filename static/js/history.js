/**
 * static/js/history.js
 * --------------------
 * Handles:
 *   - Live search/filter for backup history table
 *   - Delete backup (modal confirm → API call → row removal)
 *   - Restore backup (modal → API call)
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Live Search ──────────────────────────────────────────── */
  const searchInput = document.getElementById('historySearch');
  searchInput?.addEventListener('input', function () {
    const q = this.value.toLowerCase();
    document.querySelectorAll('.history-row').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    });
  });

  /* ── Delete Backup ────────────────────────────────────────── */
  let pendingDeleteId   = null;
  const deleteModal     = new bootstrap.Modal('#deleteModal');
  const deleteName      = document.getElementById('deleteName');
  const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');

  // Open delete confirm modal
  document.querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      pendingDeleteId = btn.dataset.id;
      deleteName.textContent = btn.dataset.name;
      deleteModal.show();
    });
  });

  // Confirm deletion
  confirmDeleteBtn?.addEventListener('click', async () => {
    if (!pendingDeleteId) return;

    confirmDeleteBtn.disabled = true;
    confirmDeleteBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Deleting…`;

    try {
      const res = await fetch(`/delete/${pendingDeleteId}`, { method: 'POST' });
      const data = await res.json();

      if (data.status === 'success') {
        // Remove the table row smoothly
        const row = document.querySelector(`.delete-btn[data-id="${pendingDeleteId}"]`)
                             ?.closest('tr');
        if (row) {
          row.style.transition = 'opacity 0.3s';
          row.style.opacity = '0';
          setTimeout(() => row.remove(), 300);
        }
        deleteModal.hide();
        showToast('Backup deleted successfully.', 'success');
      } else {
        showToast(data.message || 'Delete failed.', 'danger');
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, 'danger');
    } finally {
      confirmDeleteBtn.disabled = false;
      confirmDeleteBtn.innerHTML = `<i class="bi bi-trash3 me-1"></i>Delete`;
      pendingDeleteId = null;
    }
  });

  /* ── Restore Backup ───────────────────────────────────────── */
  let pendingRestoreId  = null;
  const restoreModal    = new bootstrap.Modal('#restoreModal');
  const restoreName     = document.getElementById('restoreName');
  const restorePath     = document.getElementById('restorePath');
  const restoreAlert    = document.getElementById('restoreAlert');
  const confirmRestoreBtn = document.getElementById('confirmRestoreBtn');

  // Open restore modal
  document.querySelectorAll('.restore-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      pendingRestoreId = btn.dataset.id;
      restoreName.textContent = btn.dataset.name;
      restorePath.value = '';
      hideAlert(restoreAlert);
      restoreModal.show();
    });
  });

  // Confirm restore
  confirmRestoreBtn?.addEventListener('click', async () => {
    const path = restorePath?.value.trim();
    if (!path) {
      showAlert(restoreAlert, 'warning', 'Please enter a restore destination path.');
      return;
    }

    confirmRestoreBtn.disabled = true;
    confirmRestoreBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Restoring…`;

    try {
      const res = await fetch('/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_id: pendingRestoreId, restore_path: path })
      });
      const data = await res.json();

      if (data.status === 'success') {
        showAlert(restoreAlert, 'success', `Restored successfully to: ${path}`);
      } else {
        showAlert(restoreAlert, 'danger', data.message || 'Restore failed.');
      }
    } catch (err) {
      showAlert(restoreAlert, 'danger', `Error: ${err.message}`);
    } finally {
      confirmRestoreBtn.disabled = false;
      confirmRestoreBtn.innerHTML = `<i class="bi bi-arrow-counterclockwise me-1"></i>Restore`;
    }
  });

  /* ── Toast Helper ─────────────────────────────────────────── */
  function showToast(msg, type = 'info') {
    // Create a floating toast in the top-right corner
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0 show position-fixed`;
    toast.style.cssText = 'top:80px; right:20px; z-index:9999; min-width:280px;';
    toast.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${msg}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto"
                data-bs-dismiss="toast"></button>
      </div>`;
    document.body.appendChild(toast);
    setTimeout(() => { toast.remove(); }, 4000);
  }

  /* ── Alert Helpers ────────────────────────────────────────── */
  function showAlert(el, type, msg) {
    if (!el) return;
    el.className = `alert alert-${type}`;
    el.textContent = msg;
    el.classList.remove('d-none');
  }

  function hideAlert(el) {
    el?.classList.add('d-none');
  }

});
