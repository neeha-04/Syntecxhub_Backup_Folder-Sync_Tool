/**
 * static/js/main.js
 * -----------------
 * Global UI behaviour:
 *   - Sidebar toggle (desktop collapse + mobile overlay)
 *   - Dark mode toggle with localStorage persistence
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Dark Mode ────────────────────────────────────────────── */
  const html       = document.documentElement;
  const darkBtn    = document.getElementById('darkModeToggle');
  const darkIcon   = document.getElementById('darkIcon');
  const DARK_KEY   = 'backuptool_dark';

  function applyTheme(dark) {
    html.setAttribute('data-bs-theme', dark ? 'dark' : 'light');
    if (darkIcon) {
      darkIcon.className = dark ? 'bi bi-sun-fill' : 'bi bi-moon-stars-fill';
    }
    localStorage.setItem(DARK_KEY, dark ? '1' : '0');
  }

  // Load saved preference (default: light)
  const savedDark = localStorage.getItem(DARK_KEY) === '1';
  applyTheme(savedDark);

  darkBtn?.addEventListener('click', () => {
    const isDark = html.getAttribute('data-bs-theme') === 'dark';
    applyTheme(!isDark);
  });

  /* ── Sidebar Toggle ───────────────────────────────────────── */
  const sidebar     = document.getElementById('sidebar');
  const mainContent = document.getElementById('main-content');
  const toggleBtn   = document.getElementById('sidebarToggle');
  const SIDE_KEY    = 'backuptool_sidebar';

  function isMobile() { return window.innerWidth < 769; }

  function setSidebar(open) {
    if (isMobile()) {
      sidebar?.classList.toggle('open', open);
    } else {
      sidebar?.classList.toggle('collapsed', !open);
      mainContent?.classList.toggle('expanded', !open);
    }
    if (!isMobile()) {
      localStorage.setItem(SIDE_KEY, open ? '1' : '0');
    }
  }

  // Restore desktop state
  if (!isMobile()) {
    const savedOpen = localStorage.getItem(SIDE_KEY) !== '0'; // default open
    setSidebar(savedOpen);
  }

  toggleBtn?.addEventListener('click', () => {
    if (isMobile()) {
      const isOpen = sidebar?.classList.contains('open');
      setSidebar(!isOpen);
    } else {
      const isCollapsed = sidebar?.classList.contains('collapsed');
      setSidebar(isCollapsed); // if collapsed → open
    }
  });

  // Close mobile sidebar on outside click
  document.addEventListener('click', (e) => {
    if (isMobile() && sidebar?.classList.contains('open')) {
      if (!sidebar.contains(e.target) && !toggleBtn?.contains(e.target)) {
        setSidebar(false);
      }
    }
  });

  // Handle resize
  window.addEventListener('resize', () => {
    if (!isMobile()) {
      sidebar?.classList.remove('open');
      const savedOpen = localStorage.getItem(SIDE_KEY) !== '0';
      setSidebar(savedOpen);
    }
  });

});
