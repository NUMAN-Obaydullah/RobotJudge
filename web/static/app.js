/* ==========================================================================
   RobotJudge-CI — Shared App Utilities
   ========================================================================== */

const API = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
    },
    async post(url, formData) {
        const res = await fetch(url, { method: 'POST', body: formData });
        if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
        return res.json();
    }
};

/* ---------- Navbar ---------- */
function renderNavbar(activePage) {
    const nav = document.getElementById('navbar');
    if (!nav) return;

    const pages = [
        { id: 'problems', label: 'Problems', href: '/', icon: '&#128221;' },
        { id: 'status', label: 'Status', href: '/status', icon: '&#128200;' },
        { id: 'submit', label: 'Submit', href: '/submit', icon: '&#128228;' },
        { id: 'ci', label: 'CI Pipeline', href: '/ci', icon: '&#9881;' },
    ];

    nav.innerHTML = `
    <a class="navbar-brand" href="/">
      <span class="brand-icon">RJ</span>
      RobotJudge
    </a>
    <ul class="navbar-nav">
      ${pages.map(p => `
        <li>
          <a href="${p.href}" class="${p.id === activePage ? 'active' : ''}">
            <span class="nav-icon">${p.icon}</span>
            ${p.label}
          </a>
        </li>
      `).join('')}
    </ul>
  `;
}

/* ---------- Verdict helpers ---------- */
function verdictBadge(status) {
    const cls = {
        'AC': 'badge-ac', 'PASS': 'badge-pass',
        'WA': 'badge-wa', 'FAIL': 'badge-fail',
        'TLE': 'badge-tle', 'MLE': 'badge-mle', 'RTE': 'badge-rte',
    }[status] || 'badge-rte';
    return `<span class="badge ${cls}">${status}</span>`;
}

function pctString(val) {
    return (val * 100).toFixed(1) + '%';
}

function costString(val) {
    if (val === undefined || val === null) return '-';
    return val.toFixed(1);
}

function msString(val) {
    if (val === undefined || val === null) return '-';
    return val + ' ms';
}

/* ---------- Table sorting ---------- */
function makeSortable(table, data, renderFn) {
    const headers = table.querySelectorAll('th[data-sort]');
    let sortKey = null;
    let sortAsc = true;

    headers.forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.sort;
            if (sortKey === key) {
                sortAsc = !sortAsc;
            } else {
                sortKey = key;
                sortAsc = true;
            }

            data.sort((a, b) => {
                let va = a[key], vb = b[key];
                if (typeof va === 'string') va = va.toLowerCase();
                if (typeof vb === 'string') vb = vb.toLowerCase();
                if (va < vb) return sortAsc ? -1 : 1;
                if (va > vb) return sortAsc ? 1 : -1;
                return 0;
            });

            // Update sort indicators
            headers.forEach(h => {
                const ind = h.querySelector('.sort-indicator');
                if (ind) {
                    if (h.dataset.sort === sortKey) {
                        ind.textContent = sortAsc ? ' \u25B2' : ' \u25BC';
                        ind.classList.add('active');
                    } else {
                        ind.textContent = ' \u25B2';
                        ind.classList.remove('active');
                    }
                }
            });

            renderFn(data);
        });
    });
}

/* ---------- Loading state ---------- */
function showLoading(container) {
    container.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      Loading...
    </div>
  `;
}

function showEmpty(container, msg) {
    container.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">&#128269;</div>
      <div class="empty-text">${msg}</div>
    </div>
  `;
}

/* ---------- Tier color ---------- */
function tierColor(tier) {
    return {
        'easy': '#4CAF50',
        'medium': '#FF9800',
        'hard': '#F44336',
    }[tier] || '#9E9E9E';
}

function tierBadge(tier) {
    const color = tierColor(tier);
    return `<span class="badge" style="background: ${color}15; color: ${color}; border: 1px solid ${color}30;">${tier}</span>`;
}
