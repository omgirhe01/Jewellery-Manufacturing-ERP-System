/* ============================================================
   SONA ERP - Main JavaScript
   API client, utilities, shared UI logic
   ============================================================ */

// ============================================================
// API CLIENT
// ============================================================
const API = {
  async request(method, path, body = null) {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (res.status === 401) { window.location.href = '/login'; return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    return data;
  },
  get: (path) => API.request('GET', path),
  post: (path, body) => API.request('POST', path, body),
  put: (path, body) => API.request('PUT', path, body),
  delete: (path) => API.request('DELETE', path),
};

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(msg, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = (type === 'success' ? '✓ ' : '✕ ') + msg;
  toast.className = `show toast-${type}`;
  setTimeout(() => { toast.className = ''; }, 3500);
}

// ============================================================
// MODAL HELPERS
// ============================================================
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('hidden');
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('hidden');
}

// Close modals on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.add('hidden');
  }
});

// ============================================================
// BADGE HELPERS
// ============================================================
function statusBadge(status) {
  const map = {
    'New': 'badge-purple', 'In Progress': 'badge-green',
    'QC Pending': 'badge-orange', 'QC Rejected': 'badge-red',
    'Completed': 'badge-gold', 'Dispatched': 'badge-blue',
    'On Hold': 'badge-gray',
  };
  return `<span class="badge ${map[status] || 'badge-gray'}">${status}</span>`;
}

function metalBadge(metal) {
  const map = {
    '24K': 'badge-gold', '22K': 'badge-gold', '18K': 'badge-orange',
    'Silver': 'badge-blue', 'Other': 'badge-gray'
  };
  return `<span class="badge ${map[metal] || 'badge-gray'}">${metal}</span>`;
}

function priorityBadge(p) {
  const map = { 'Normal': 'badge-gray', 'High': 'badge-orange', 'Urgent': 'badge-red' };
  return `<span class="badge ${map[p] || 'badge-gray'}">${p}</span>`;
}

// ============================================================
// WEIGHT PROGRESS BAR
// ============================================================
function weightBar(current, target) {
  const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
  const color = pct >= 95 ? '#4cc96f' : pct >= 70 ? '#C9A84C' : '#e07b3b';
  return `
    <div style="font-size:11px">${current}g <span class="text-muted">/ ${target}g</span></div>
    <div class="weight-progress">
      <div class="weight-fill" style="width:${pct}%;background:${color}"></div>
    </div>`;
}

// ============================================================
// STAGE PIPELINE
// ============================================================
const STAGE_COLORS = {
  'Design': '#C9A84C', 'Wax / CAM': '#b57bee', 'Casting': '#e07b3b',
  'Filing / Pre-Polish': '#4ca8c9', 'Stone Setting': '#e0b43b',
  'Polishing': '#4cc9a8', 'Quality Control': '#c94c6f', 'Dispatch': '#4cc96f'
};

function renderPipeline(stages, container) {
  if (!container) return;
  container.innerHTML = stages.map(s => `
    <div class="pipeline-stage">
      <div class="pipeline-bar-fill" style="background:${s.count > 0 ? STAGE_COLORS[s.name] || '#C9A84C' : '#2a2318'};
        box-shadow:${s.count > 0 ? `0 0 6px ${STAGE_COLORS[s.name] || '#C9A84C'}66` : 'none'}"></div>
      <div class="pipeline-count" style="color:${s.count > 0 ? STAGE_COLORS[s.name] || '#C9A84C' : '#3a3020'}">${s.count}</div>
      <div class="pipeline-name">${s.name}</div>
    </div>`).join('');
}

// ============================================================
// DATE FORMATTING
// ============================================================
function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}
function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

// ============================================================
// NUMBER FORMATTING
// ============================================================
function fmtWt(val) { return val != null ? parseFloat(val).toFixed(3) + 'g' : '—'; }
function fmtCur(val) { return '₹' + parseFloat(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 }); }
function fmtPct(val) { return parseFloat(val || 0).toFixed(2) + '%'; }

// ============================================================
// DEBOUNCE
// ============================================================
function debounce(fn, delay = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ============================================================
// LOGOUT
// ============================================================
async function logout() {
  await API.post('/api/v1/auth/logout');
  window.location.href = '/login';
}

// ============================================================
// FORM DATA HELPER
// ============================================================
function formToObj(formId) {
  const form = document.getElementById(formId);
  if (!form) return {};
  const data = {};
  new FormData(form).forEach((v, k) => {
    data[k] = v === '' ? null : isNaN(v) || v === '' ? v : Number(v);
  });
  return data;
}

// ============================================================
// BARCODE SCANNER (keyboard wedge)
// ============================================================
let barcodeBuffer = '';
let barcodeTimer = null;
function initBarcodeScanner(onScan) {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && barcodeBuffer.length > 4) {
      onScan(barcodeBuffer);
      barcodeBuffer = '';
      clearTimeout(barcodeTimer);
      return;
    }
    if (e.key.length === 1) {
      barcodeBuffer += e.key;
      clearTimeout(barcodeTimer);
      barcodeTimer = setTimeout(() => { barcodeBuffer = ''; }, 150);
    }
  });
}

// ============================================================
// POPULATE SELECT FROM API
// ============================================================
async function populateSelect(selectId, url, valueKey, labelKey, placeholder = '— Select —') {
  const el = document.getElementById(selectId);
  if (!el) return;
  try {
    const data = await API.get(url);
    const items = data.items || data;
    el.innerHTML = `<option value="">${placeholder}</option>` +
      items.map(i => `<option value="${i[valueKey]}">${i[labelKey]}</option>`).join('');
  } catch (e) { console.error('populateSelect error', e); }
}
