/**
 * main.js — Global MediaFlow application utilities
 * Loaded on every page via base.html
 */

// ── Global namespace ──────────────────────────────────────────────────────
window.MF = window.MF || {};

// ── CSRF Token helper ─────────────────────────────────────────────────────
window.MF.getCsrf = function() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.content;
  const input = document.querySelector('[name=csrfmiddlewaretoken]');
  if (input) return input.value;
  // Read from cookie
  const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
  return cookie ? cookie.split('=')[1].trim() : '';
};

// ── Toast system ──────────────────────────────────────────────────────────
window.MF.toast = function(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const icons = {
    success: '✓',
    error:   '✕',
    warning: '⚠',
    info:    'ℹ',
  };

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="toast-icon">${icons[type] || 'ℹ'}</div>
    <div class="toast-body">
      <div class="toast-message">${escapeHtml(message)}</div>
    </div>
    <div class="toast-close" onclick="this.closest('.toast').remove()">✕</div>`;

  container.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => {
      toast.style.animation = 'fadeOut 0.3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
};

// ── HTML escaping ─────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Theme management ──────────────────────────────────────────────────────
(function initTheme() {
  const html = document.documentElement;
  const icon = document.getElementById('themeIcon');
  const btn  = document.getElementById('themeToggle');

  function applyTheme(theme) {
    html.setAttribute('data-theme', theme);
    if (icon) {
      icon.className = theme === 'dark' ? 'bi bi-moon-stars' : 'bi bi-sun';
    }
    localStorage.setItem('mf-theme', theme);
  }

  // On load: respect localStorage override, then fall back to server setting
  const saved = localStorage.getItem('mf-theme');
  if (saved) applyTheme(saved);

  if (btn) {
    btn.addEventListener('click', () => {
      const current = html.getAttribute('data-theme') || 'dark';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    });
  }
})();

// ── Mobile sidebar ────────────────────────────────────────────────────────
(function initSidebar() {
  const toggleBtn = document.getElementById('sidebarToggle');
  const sidebar   = document.getElementById('sidebar');
  if (!toggleBtn || !sidebar) return;

  toggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('mobile-open');
  });

  // Close on outside click
  document.addEventListener('click', e => {
    if (
      sidebar.classList.contains('mobile-open') &&
      !sidebar.contains(e.target) &&
      e.target !== toggleBtn
    ) {
      sidebar.classList.remove('mobile-open');
    }
  });
})();

// ── Active job count (sidebar badge) ─────────────────────────────────────
(function pollSidebarCount() {
  const badge = document.getElementById('sidebar-active-count');
  if (!badge) return;

  setInterval(async () => {
    try {
      const r = await fetch('/queue/status/');
      const d = await r.json();
      if (d.ok) {
        const count = d.downloads.length + d.conversions.length;
        badge.textContent = count;
        badge.style.display = count > 0 ? '' : 'none';
      }
    } catch(e) {}
  }, 5000);
})();
