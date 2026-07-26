// Mockup-only interactivity: theme toggle, sidebar collapse, tabs, slide-over, dropdown.
// None of this ships in the real frontend/ app — it exists so the token/motion
// system can be judged live in a browser rather than as a static screenshot.

document.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement;
  const themeBtn = document.querySelector('[data-theme-toggle]');
  if (themeBtn) {
    const icon = themeBtn.querySelector('use');
    themeBtn.addEventListener('click', () => {
      const current = root.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      icon.setAttribute('href', next === 'dark' ? '#i-sun' : '#i-moon');
      themeBtn.lastChild.textContent = next === 'dark' ? ' Light mode' : ' Dark mode';
    });
  }

  const sidebar = document.querySelector('.sidebar');
  const sideToggle = document.querySelector('[data-sidebar-toggle]');
  if (sidebar && sideToggle) {
    sideToggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));
  }

  // Sidebar resize: drag the right-edge handle, clamp 170-420px (§3), same
  // accent-highlight-on-drag treatment as the grid's column resize handle.
  const resizeHandle = document.querySelector('[data-sidebar-resize]');
  if (sidebar && resizeHandle) {
    let dragging = false;
    resizeHandle.addEventListener('mousedown', (e) => {
      if (sidebar.classList.contains('collapsed')) return;
      dragging = true;
      resizeHandle.classList.add('dragging');
      sidebar.classList.add('resizing');
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const rect = sidebar.getBoundingClientRect();
      const width = Math.min(420, Math.max(170, e.clientX - rect.left));
      document.documentElement.style.setProperty('--sidebar-w', `${width}px`);
    });
    window.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      resizeHandle.classList.remove('dragging');
      sidebar.classList.remove('resizing');
      document.body.style.userSelect = '';
    });
  }

  document.querySelectorAll('[data-tabs]').forEach((group) => {
    const tabs = group.querySelectorAll('.tab');
    const panels = document.querySelectorAll(`[data-tab-panel-group="${group.dataset.tabs}"]`);
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        tabs.forEach((t) => t.classList.remove('active'));
        panels.forEach((p) => p.classList.remove('active'));
        tab.classList.add('active');
        document.querySelector(`[data-tab-panel="${tab.dataset.tab}"]`)?.classList.add('active');
      });
    });
  });

  const scrim = document.querySelector('[data-scrim]');
  const slideover = document.querySelector('[data-slideover]');
  document.querySelectorAll('[data-open-slideover]').forEach((btn) => {
    btn.addEventListener('click', () => {
      scrim?.classList.add('open');
      slideover?.classList.add('open');
    });
  });
  document.querySelectorAll('[data-close-slideover]').forEach((btn) => {
    btn.addEventListener('click', () => {
      scrim?.classList.remove('open');
      slideover?.classList.remove('open');
    });
  });
  scrim?.addEventListener('click', () => {
    scrim.classList.remove('open');
    slideover?.classList.remove('open');
  });

  document.querySelectorAll('[data-dropdown-toggle]').forEach((btn) => {
    const menu = btn.parentElement.querySelector('.dropdown-menu');
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      menu?.classList.toggle('open');
    });
  });
  document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown-menu.open').forEach((m) => m.classList.remove('open'));
  });

  // Sort headers: same three-state affordance (neutral -> asc -> desc -> neutral)
  // whether the column is client-sorted or server-sorted. Server columns
  // (data-server="true") show a brief spinner and dim the other sortable
  // headers, demonstrating that the *only* difference is latency feedback.
  const ICONS = { none: 'i-sort', asc: 'i-arrow-up', desc: 'i-arrow-down' };
  const NEXT = { none: 'asc', asc: 'desc', desc: 'none' };
  document.querySelectorAll('.sort-trigger').forEach((btn) => {
    btn.addEventListener('click', () => {
      const th = btn.closest('th');
      const group = th.closest('table').querySelectorAll('th.sortable');
      const isServer = th.dataset.server === 'true';
      const applyState = (state) => {
        const icon = btn.querySelector('.sort-icon use');
        icon.setAttribute('href', `#${ICONS[state]}`);
        btn.querySelector('.sort-icon').classList.toggle('active', state !== 'none');
        th.dataset.sortState = state;
      };
      const current = th.dataset.sortState || 'none';
      const nextState = NEXT[current];
      if (!isServer) { applyState(nextState); return; }
      const icon = btn.querySelector('.sort-icon use');
      icon.setAttribute('href', '#i-spinner');
      btn.querySelector('.sort-icon').classList.add('spin');
      group.forEach((other) => { if (other !== th) other.classList.add('sort-disabled'); });
      setTimeout(() => {
        btn.querySelector('.sort-icon').classList.remove('spin');
        applyState(nextState);
        group.forEach((other) => other.classList.remove('sort-disabled'));
      }, 700);
    });
  });

  // Command palette (⌘K / Ctrl+K) — one index onto the same tables/
  // changesets the sidebar and queue already expose (§3), not a parallel
  // feature. Arrow keys move the selection, Enter activates it.
  const cmdk = document.querySelector('[data-cmdk]');
  const cmdkScrim = document.querySelector('[data-cmdk-scrim]');
  const cmdkInput = document.querySelector('[data-cmdk-input]');
  const cmdkResults = document.querySelector('[data-cmdk-results]');
  const cmdkEmpty = document.querySelector('[data-cmdk-empty]');
  if (cmdk && cmdkInput && cmdkResults) {
    const items = () => Array.from(cmdkResults.querySelectorAll('.cmdk-item'));

    const filterCmdk = (raw) => {
      const q = raw.trim().toLowerCase();
      let anyVisible = false;
      let lastGroup = null;
      let groupHasVisible = false;
      Array.from(cmdkResults.children).forEach((node) => {
        if (node.classList.contains('cmdk-group')) {
          if (lastGroup) lastGroup.hidden = !groupHasVisible;
          lastGroup = node;
          groupHasVisible = false;
          return;
        }
        const match = !q || node.textContent.toLowerCase().includes(q);
        node.hidden = !match;
        if (match) { groupHasVisible = true; anyVisible = true; }
      });
      if (lastGroup) lastGroup.hidden = !groupHasVisible;
      items().forEach((el) => el.classList.remove('selected'));
      const first = items().find((el) => !el.hidden);
      first?.classList.add('selected');
      if (cmdkEmpty) cmdkEmpty.hidden = anyVisible;
    };

    const openCmdk = () => {
      cmdk.classList.add('open');
      cmdkScrim?.classList.add('open');
      cmdkInput.value = '';
      filterCmdk('');
      setTimeout(() => cmdkInput.focus(), 10);
    };
    const closeCmdk = () => {
      cmdk.classList.remove('open');
      cmdkScrim?.classList.remove('open');
    };

    document.querySelectorAll('[data-open-cmdk]').forEach((btn) => btn.addEventListener('click', openCmdk));
    cmdkScrim?.addEventListener('click', closeCmdk);
    cmdkInput.addEventListener('input', () => filterCmdk(cmdkInput.value));

    items().forEach((item) => {
      item.addEventListener('click', () => {
        if (item.dataset.action === 'theme') {
          document.querySelector('[data-theme-toggle]')?.click();
          closeCmdk();
          return;
        }
        const href = item.dataset.href;
        closeCmdk();
        if (href) window.location.href = href;
      });
    });

    document.addEventListener('keydown', (e) => {
      const isOpen = cmdk.classList.contains('open');
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        isOpen ? closeCmdk() : openCmdk();
        return;
      }
      if (!isOpen) return;
      if (e.key === 'Escape') { closeCmdk(); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const visible = items().filter((el) => !el.hidden);
        if (!visible.length) return;
        let idx = visible.findIndex((el) => el.classList.contains('selected'));
        visible[idx]?.classList.remove('selected');
        idx = e.key === 'ArrowDown' ? (idx + 1) % visible.length : (idx - 1 + visible.length) % visible.length;
        visible[idx].classList.add('selected');
        visible[idx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        const selected = items().find((el) => el.classList.contains('selected') && !el.hidden);
        selected?.click();
      }
    });
  }

  // Toasts (§6) — one shared stack; supplements inline errors, never replaces them.
  window.showToast = (message, variant = 'success') => {
    const stack = document.querySelector('[data-toast-stack]');
    if (!stack) return;
    const iconId = variant === 'error' ? 'i-close' : variant === 'info' ? 'i-info' : 'i-check';
    const el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = `
      <svg class="icon toast-icon ${variant}"><use href="#${iconId}"></use></svg>
      <span class="toast-message"></span>
      <button class="icon-btn" aria-label="Dismiss"><svg class="icon icon-sm"><use href="#i-close"></use></svg></button>
      <span class="toast-progress"></span>
    `;
    el.querySelector('.toast-message').textContent = message;
    stack.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    const dismiss = () => {
      el.classList.remove('show');
      el.classList.add('leaving');
      setTimeout(() => el.remove(), 260);
    };
    el.querySelector('button').addEventListener('click', dismiss);
    setTimeout(dismiss, 4200);
  };
  document.querySelectorAll('[data-toast-trigger]').forEach((btn) => {
    btn.addEventListener('click', () => {
      window.showToast(btn.dataset.toastMessage || 'Done', btn.dataset.toastVariant || 'success');
    });
  });
});
