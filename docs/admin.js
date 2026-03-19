const REVIEW_STORAGE_KEY = 'cs-deadlines-admin-review-draft-v1';
const THEME_STORAGE_KEY = 'cs-deadlines-theme-v1';
const ADMIN_AUTH_STORAGE_KEY = 'cs-deadlines-admin-auth-ok-v1';
const ADMIN_PASSWORD_SHA256 = 'f1f5175cac7219d5274210b1b36acd6e2693a84fe41be92d5810cca2dd7104ff';

let baseRecords = [];
let reviewDraft = loadDraft();

async function loadAdminData() {
  const paths = ['./assets/admin.json', './assets/venues.json', './venues.json'];
  for (const path of paths) {
    try {
      const res = await fetch(path);
      if (res.ok) return await res.json();
    } catch (err) {}
  }
  return [];
}

function norm(v) { return String(v || '').toLowerCase(); }

function draftEntryFor(recordOrId) {
  const id = typeof recordOrId === 'string' ? recordOrId : recordOrId.id;
  return reviewDraft.records?.[id] || null;
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(REVIEW_STORAGE_KEY);
    if (!raw) return { records: {}, updated_at: null };
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return { records: {}, updated_at: null };
    return { records: parsed.records || {}, updated_at: parsed.updated_at || null };
  } catch (err) {
    return { records: {}, updated_at: null };
  }
}

function safeStorageGet(key) {
  try {
    return localStorage.getItem(key);
  } catch (err) {
    return null;
  }
}

function safeStorageSet(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (err) {}
}

function safeSessionGet(key) {
  try {
    return sessionStorage.getItem(key);
  } catch (err) {
    return null;
  }
}

function safeSessionSet(key, value) {
  try {
    sessionStorage.setItem(key, value);
  } catch (err) {}
}

async function sha256Hex(text) {
  if (!window.crypto?.subtle || typeof TextEncoder === 'undefined') return '';
  const bytes = new TextEncoder().encode(text);
  const digest = await window.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

async function verifyAdminPassword() {
  // This is a lightweight client-side gate for casual protection, not real authentication.
  if (safeSessionGet(ADMIN_AUTH_STORAGE_KEY) === '1') return true;
  const input = window.prompt('Admin password');
  if (input === null) return false;
  const hashed = await sha256Hex(input);
  const ok = hashed === ADMIN_PASSWORD_SHA256;
  if (ok) safeSessionSet(ADMIN_AUTH_STORAGE_KEY, '1');
  return ok;
}

function applyTheme(theme) {
  // Keep theme behavior shared with the public page so the admin UI feels consistent.
  const next = theme === 'light' ? 'light' : 'dark';
  document.body.dataset.theme = next;
  const toggle = document.getElementById('themeToggle');
  if (toggle) {
    const isLight = next === 'light';
    const nextLabel = isLight ? 'Switch to black theme' : 'Switch to white theme';
    toggle.classList.toggle('is-light', isLight);
    toggle.setAttribute('aria-pressed', isLight ? 'true' : 'false');
    toggle.setAttribute('aria-label', nextLabel);
    toggle.setAttribute('title', nextLabel);
    const label = toggle.querySelector('.theme-label');
    if (label) label.textContent = isLight ? 'WHITE' : 'BLACK';
  }
}

function initThemeToggle() {
  const saved = safeStorageGet(THEME_STORAGE_KEY);
  applyTheme(saved === 'light' ? 'light' : 'dark');
  const toggle = document.getElementById('themeToggle');
  if (!toggle) return;
  toggle.addEventListener('click', () => {
    const current = document.body.dataset.theme === 'light' ? 'light' : 'dark';
    const next = current === 'light' ? 'dark' : 'light';
    applyTheme(next);
    safeStorageSet(THEME_STORAGE_KEY, next);
  });
}

function sanitizeHttpUrl(value) {
  if (!value) return null;
  try {
    const u = new URL(String(value), window.location.href);
    // Restrict to http/https links when rendering untrusted data.
    if (u.protocol === 'http:' || u.protocol === 'https:') return u.href;
    return null;
  } catch (err) {
    return null;
  }
}

function appendSafeLink(container, label, rawUrl) {
  const safe = sanitizeHttpUrl(rawUrl);
  if (!safe) return false;
  const a = document.createElement('a');
  a.href = safe;
  a.target = '_blank';
  a.rel = 'noopener';
  a.textContent = label;
  container.appendChild(a);
  return true;
}

function renderSafeLinks(container, links) {
  container.innerHTML = '';
  const valid = links.filter(link => sanitizeHttpUrl(link.url));
  valid.forEach((link, idx) => {
    appendSafeLink(container, link.label, link.url);
    if (idx < valid.length - 1) {
      const sep = document.createElement('span');
      sep.className = 'dot';
      sep.textContent = '·';
      container.appendChild(document.createTextNode(' '));
      container.appendChild(sep);
      container.appendChild(document.createTextNode(' '));
    }
  });
}

function saveDraftToStorage() {
  reviewDraft.updated_at = new Date().toISOString();
  localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify(reviewDraft, null, 2));
  updateDraftStatus();
}

function clearDraft() {
  reviewDraft = { records: {}, updated_at: null };
  localStorage.removeItem(REVIEW_STORAGE_KEY);
  updateDraftStatus();
  render(baseRecords);
}

function updateDraftStatus() {
  const count = Object.keys(reviewDraft.records || {}).length;
  const text = count
    ? `${count} local draft change${count === 1 ? '' : 's'} saved${reviewDraft.updated_at ? ` · ${new Date(reviewDraft.updated_at).toLocaleString()}` : ''}`
    : 'No local draft yet.';
  document.getElementById('draftStatus').textContent = text;
}

function mergeRecord(base) {
  const patch = draftEntryFor(base);
  if (!patch) return { ...base, _draftEdited: false };
  // The admin UI always renders a local merged view before anything is exported back to disk.
  const merged = structuredClone(base);
  if (patch.status !== undefined) merged.status = patch.status;
  if (patch.notes !== undefined) merged.notes = patch.notes;
  if (patch.source_url !== undefined) merged.source_url = patch.source_url;
  if (patch.location !== undefined) merged.location = patch.location;
  if (patch.confidence !== undefined) merged.confidence = patch.confidence;
  if (patch.checked_at !== undefined) merged.checked_at = patch.checked_at;
  if (patch.scan_preview !== undefined) merged.scan_preview = patch.scan_preview;
  if (Array.isArray(patch.deadlines)) merged.deadlines = patch.deadlines;
  merged._draftEdited = true;
  merged._draftPatch = patch;
  return merged;
}

function bucketFor(record) {
  // Buckets are presentation-level groupings layered on top of raw pipeline statuses.
  const s = norm(record.status);
  if (['confirmed', 'auto_confirmed', 'closed', 'approved'].includes(s)) return 'confirmed';
  if (['scan_failed', 'rejected'].includes(s)) return 'failed';
  if (['scanned', 'review_required', 'conflict'].includes(s)) return 'review';
  if (['catalog_seed', 'placeholder', 'awaiting_cfp'].includes(s)) return 'catalog';
  if ((record.scan_preview || []).length) return 'review';
  if ((record.deadlines || []).length) return 'confirmed';
  return 'catalog';
}

function effectiveBucket(record) {
  return norm(record.status) === 'scan_failed' ? 'failed' : bucketFor(record);
}

function areas(record) {
  const raw = (record.domain || []).map(d => norm(d));
  const out = new Set();
  raw.forEach(d => {
    if (['ai','machine-learning','ml','nlp','vision','computer-vision','data-mining','databases','db','ir','information-retrieval','data','kdd'].includes(d)) out.add('AI+Data');
    if (['systems','networking','cloud','distributed-systems','architecture','computer-architecture','operating-systems'].includes(d)) out.add('Systems');
    if (['security','privacy','cryptography','crypto'].includes(d)) out.add('Security');
    if (['software-engineering','se','programming-languages','pl','theory','formal-methods','verification','compilers'].includes(d)) out.add('SE+Theory');
    if (['human-computer-interaction', 'hci', 'graphics', 'visualization', 'vision-and-graphics'].includes(d)) out.add('HCI+Graphics');
  });
  if (!out.size) out.add('AI+Data');
  return Array.from(out).join(' / ');
}

function parseDate(v) {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function isPlausibleParsedYear(date, conferenceYear, allowFullPrevYear = false) {
  if (!conferenceYear) return true;
  const y = date.getUTCFullYear();
  const m = date.getUTCMonth() + 1;
  if (y === conferenceYear) return true;
  if (y === conferenceYear - 1 && m >= 8) return true;
  if (allowFullPrevYear && y === conferenceYear - 1) return true;
  if (y === conferenceYear + 1 && m <= 2) return true;
  return false;
}

function parsedDeadlineItems(record) {
  const conferenceYear = Number(record.year || 0);
  // Parsed candidates are useful for review, but still filtered to avoid obvious junk.
  return (record.parsed_deadlines || [])
    .map(d => ({
      kind: d.kind || 'deadline',
      value: d.value,
      confidence: typeof d.confidence === 'number' ? d.confidence : Number(d.confidence || 0),
      date: parseDate(d.value),
      year_fallback: !!d.year_fallback,
      source: 'parsed'
    }))
    .filter(d => d.date)
    .filter(d => d.confidence >= 0.35)
    .filter(d => isPlausibleParsedYear(d.date, conferenceYear, d.year_fallback));
}

function hasPreviewDeadline(record) {
  return parsedDeadlineItems(record).length > 0;
}

function nextDeadline(record) {
  let items = (record.deadlines || [])
    .map(d => ({ ...d, confidence: null, date: parseDate(d.value), source: 'confirmed' }))
    .filter(d => d.date)
    .sort((a, b) => a.date - b.date);

  if (!items.length) {
    items = parsedDeadlineItems(record)
      .sort((a, b) => (b.confidence - a.confidence) || (a.date - b.date));
  }

  const now = Date.now();
  const upcoming = items.find(d => d.date.getTime() > now);
  return upcoming || items[0] || null;
}

function deadlineStatusText(record, nd) {
  if (nd) {
    const prefix = nd.source === 'parsed' ? 'Candidate deadline (needs review)' : (nd.kind || 'deadline');
    const suffix = nd.source === 'parsed'
      ? ` (confidence ${(nd.confidence ?? 0).toFixed(2)})`
      : '';
    return `${prefix}: ${formatWhen(nd.value)}${suffix}`;
  }
  if (!record.scan_enabled) return 'No structured deadline (catalog/manual venue)';
  const notes = (record.notes || '').toLowerCase();
  if (record.status === 'scan_failed' || notes.includes('fetch failed')) {
    return 'No structured deadline (scan failed: check source access)';
  }
  if ((record.scan_preview || []).length > 0) {
    return 'No structured deadline (date text not found in extracted lines)';
  }
  return 'No structured deadline available';
}

function formatWhen(value) {
  const d = parseDate(value);
  return d ? d.toLocaleString() : '—';
}

function haystack(record) {
  const patch = draftEntryFor(record);
  return [
    record.title,
    record.short_name,
    ...(record.aliases || []),
    ...(record.domain || []),
    record.parser,
    record.notes,
    record.source_url,
    record.status,
    areas(record),
    patch ? 'edited draft pending' : ''
  ].join(' ').toLowerCase();
}

function statusOptions(records) {
  return Array.from(new Set(records.map(r => r.status).filter(Boolean))).sort();
}

function passesFilters(record) {
  const q = norm(document.getElementById('adminSearch').value.trim());
  const bucket = document.getElementById('bucketFilter').value;
  const parser = document.getElementById('parserFilter').value;
  const status = document.getElementById('statusFilter').value;
  const scanEnabledOnly = document.getElementById('scanEnabledOnly').checked;
  const activeOnly = document.getElementById('activeOnly').checked;
  const previewOnly = document.getElementById('previewOnly').checked;
  const editedOnly = document.getElementById('editedOnly').checked;

  if (q && !haystack(record).includes(q)) return false;
  if (bucket && effectiveBucket(record) !== bucket) return false;
  if (parser && record.parser !== parser) return false;
  if (status && record.status !== status) return false;
  if (scanEnabledOnly && !record.scan_enabled) return false;
  if (activeOnly && record.active === false) return false;
  if (previewOnly && !hasPreviewDeadline(record)) return false;
  if (editedOnly && !record._draftEdited) return false;
  return true;
}

function summaryCounts(records) {
  const counts = { total: records.length, confirmed: 0, review: 0, catalog: 0, failed: 0, edited: 0 };
  records.forEach(r => {
    counts[effectiveBucket(r)] = (counts[effectiveBucket(r)] || 0) + 1;
    if (r._draftEdited) counts.edited += 1;
  });
  return counts;
}

function confidenceText(record) {
  if (typeof record.confidence === 'number') return record.confidence.toFixed(2);
  return '—';
}

function createBadges(record) {
  const bucket = effectiveBucket(record);
  return [
    `<span class="badge ${bucket}">${bucket}</span>`,
    `<span class="badge raw-status">${record.status || 'unknown'}</span>`,
    `<span class="badge parser">${record.parser || 'n/a'}</span>`,
    `<span class="badge scan">${record.scan_enabled ? 'scan enabled' : 'catalog only'}</span>`,
    record._draftEdited ? `<span class="badge edited">draft edited</span>` : ''
  ].join(' ');
}

function renderSummary(records) {
  const counts = summaryCounts(records);
  const root = document.getElementById('summaryCards');
  root.innerHTML = `
    <div class="summary-card"><div class="summary-label">Visible records</div><div class="summary-value">${counts.total}</div></div>
    <div class="summary-card"><div class="summary-label">Confirmed</div><div class="summary-value">${counts.confirmed || 0}</div></div>
    <div class="summary-card"><div class="summary-label">Review queue</div><div class="summary-value">${counts.review || 0}</div></div>
    <div class="summary-card"><div class="summary-label">Catalog seed</div><div class="summary-value">${counts.catalog || 0}</div></div>
    <div class="summary-card"><div class="summary-label">Failures</div><div class="summary-value">${counts.failed || 0}</div></div>
    <div class="summary-card"><div class="summary-label">Draft edits</div><div class="summary-value">${counts.edited || 0}</div></div>
  `;
}

function defaultDraftPatch(record) {
  // Exported review patches mirror the subset of fields that local scripts know how to apply.
  return {
    id: record.id,
    venue_id: record.venue_id,
    year: record.year,
    status: record.status,
    deadlines: Array.isArray(record.deadlines) ? structuredClone(record.deadlines) : [],
    location: record.location || null,
    source_url: record.source_url || record.cfp_url || record.website || null,
    confidence: typeof record.confidence === 'number' ? record.confidence : null,
    checked_at: new Date().toISOString(),
    notes: record.notes || '',
    scan_preview: Array.isArray(record.scan_preview) ? structuredClone(record.scan_preview) : [],
  };
}

function upsertDraftPatch(record, updater) {
  const existing = draftEntryFor(record) || defaultDraftPatch(record);
  const next = updater(structuredClone(existing));
  next.id = record.id;
  next.venue_id = record.venue_id;
  next.year = record.year;
  next.checked_at = new Date().toISOString();
  reviewDraft.records[record.id] = next;
  saveDraftToStorage();
  render(baseRecords);
}

function setQuickStatus(record, status) {
  upsertDraftPatch(record, patch => {
    patch.status = status;
    if (status === 'confirmed' && (!patch.deadlines || !patch.deadlines.length) && Array.isArray(record.deadlines) && record.deadlines.length) {
      patch.deadlines = structuredClone(record.deadlines);
    }
    return patch;
  });
}

function removeDraftPatch(record) {
  delete reviewDraft.records[record.id];
  saveDraftToStorage();
  render(baseRecords);
}

function buildDeadlineRows(deadlines) {
  const safe = Array.isArray(deadlines) && deadlines.length ? deadlines : [{ kind: 'deadline', value: '' }];
  return safe.map((deadline, index) => `
    <div class="deadline-row" data-index="${index}">
      <input type="text" name="deadlineKind" value="${escapeHtml(deadline.kind || '')}" placeholder="kind (e.g. abstract, paper)" />
      <input type="datetime-local" name="deadlineValue" value="${toDatetimeLocal(deadline.value)}" />
      <button type="button" class="btn tiny danger ghost" data-action="remove-deadline" data-index="${index}">Remove</button>
    </div>
  `).join('');
}

function createEditPanel(record) {
  const patch = draftEntryFor(record) || defaultDraftPatch(record);
  return `
    <details class="edit-box" ${record._draftEdited ? 'open' : ''}>
      <summary>${record._draftEdited ? 'Edit saved draft' : 'Edit record'}</summary>
      <form class="edit-form" data-record-id="${record.id}">
        <div class="form-grid">
          <label>
            <span>Status</span>
            <select name="status">
              ${['scanned','review_required','confirmed','auto_confirmed','scan_failed','rejected','catalog_seed','placeholder','awaiting_cfp','closed'].map(status => `<option value="${status}" ${patch.status === status ? 'selected' : ''}>${status}</option>`).join('')}
            </select>
          </label>
          <label>
            <span>Location</span>
            <input type="text" name="location" value="${escapeHtml(patch.location || '')}" placeholder="e.g. Paris, France" />
          </label>
          <label>
            <span>Source URL</span>
            <input type="url" name="source_url" value="${escapeHtml(patch.source_url || '')}" placeholder="https://..." />
          </label>
          <label>
            <span>Confidence</span>
            <input type="number" step="0.01" min="0" max="1" name="confidence" value="${patch.confidence ?? ''}" placeholder="0.00" />
          </label>
        </div>
        <label>
          <span>Notes</span>
          <textarea name="notes" rows="3" placeholder="Manual review notes">${escapeHtml(patch.notes || '')}</textarea>
        </label>
        <div>
          <div class="field-label">Deadlines</div>
          <div class="deadline-list">${buildDeadlineRows(patch.deadlines)}</div>
          <div class="inline-actions">
            <button type="button" class="btn tiny secondary" data-action="add-deadline">Add deadline</button>
          </div>
        </div>
        <div class="edit-actions">
          <button type="submit" class="btn">Save record draft</button>
          <button type="button" class="btn secondary" data-action="approve">Approve</button>
          <button type="button" class="btn danger" data-action="reject">Reject</button>
          <button type="button" class="btn ghost" data-action="discard-draft">Discard draft</button>
        </div>
      </form>
    </details>
  `;
}

function renderList(targetId, records) {
  const root = document.getElementById(targetId);
  const tpl = document.getElementById('adminRowTemplate');
  root.innerHTML = '';
  if (!records.length) {
    root.innerHTML = '<div class="empty-state">Nothing to show in this section.</div>';
    return;
  }
  records.forEach(record => {
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.recordId = record.id;
    node.querySelector('.admin-title').textContent = `${record.short_name} — ${record.title}`;
    node.querySelector('.admin-meta').textContent = `${areas(record)} · ${record.year || '—'} · ${record.location || 'Location TBD'} · confidence ${confidenceText(record)}`;
    node.querySelector('.admin-badges').innerHTML = createBadges(record);
    const nd = nextDeadline(record);
    node.querySelector('.admin-deadline').textContent = deadlineStatusText(record, nd);
    renderSafeLinks(node.querySelector('.admin-links'), [
      { label: 'Venue', url: record.website },
      { label: 'CFP', url: record.cfp_url },
      { label: 'Source', url: record.source_url }
    ]);
    node.querySelector('.admin-actions').innerHTML = `
      <button class="btn tiny" data-action="approve">Approve</button>
      <button class="btn tiny danger" data-action="reject">Reject</button>
      <button class="btn tiny secondary" data-action="toggle-edit">Edit</button>
      ${record._draftEdited ? '<button class="btn tiny ghost" data-action="discard-draft">Discard draft</button>' : ''}
    `;
    node.querySelector('.admin-edit-panel').innerHTML = createEditPanel(record);
    node.querySelector('.detail-notes').textContent = record.notes || '—';
    const preview = (record.scan_preview || []).length ? `<ul>${record.scan_preview.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>` : '—';
    node.querySelector('.detail-preview').innerHTML = preview;
    root.appendChild(node);
  });
}

function renderTable(records) {
  const tbody = document.querySelector('#adminTable tbody');
  tbody.innerHTML = '';
  records.forEach(record => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${escapeHtml(record.short_name)}</strong><br><span class="table-sub">${escapeHtml(record.title)}</span></td>
      <td>${escapeHtml(effectiveBucket(record))}</td>
      <td>${escapeHtml(record.status || '—')}</td>
      <td>${escapeHtml(record.parser || '—')}</td>
      <td>${record.scan_enabled ? 'enabled' : 'catalog'}</td>
      <td>${escapeHtml(confidenceText(record))}</td>
      <td>${record.checked_at ? escapeHtml(formatWhen(record.checked_at)) : '—'}</td>
      <td class="source-link-cell">—</td>
      <td>${record._draftEdited ? '<span class="table-draft">pending draft</span>' : '—'}</td>
    `;
    const sourceCell = tr.querySelector('.source-link-cell');
    if (sourceCell) {
      sourceCell.innerHTML = '';
      if (!appendSafeLink(sourceCell, 'open', record.source_url)) {
        sourceCell.textContent = '—';
      }
    }
    tbody.appendChild(tr);
  });
}

function sortRecords(records) {
  return records.slice().sort((a, b) => {
    const order = { review: 0, failed: 1, confirmed: 2, catalog: 3 };
    return (order[effectiveBucket(a)] ?? 9) - (order[effectiveBucket(b)] ?? 9)
      || (b._draftEdited === true) - (a._draftEdited === true)
      || String(a.short_name || '').localeCompare(String(b.short_name || ''));
  });
}

function mergedRecords() {
  return baseRecords.map(mergeRecord);
}

function render(records) {
  const merged = records.map(mergeRecord);
  const filtered = sortRecords(merged.filter(passesFilters));
  // One filter pass drives every admin section so counts and lists stay aligned.
  renderSummary(filtered);
  renderList('reviewQueue', filtered.filter(r => ['review','failed'].includes(effectiveBucket(r))));
  renderList('catalogSeeds', filtered.filter(r => effectiveBucket(r) === 'catalog'));
  renderList('scanFailures', filtered.filter(r => effectiveBucket(r) === 'failed'));
  renderTable(filtered);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function toDatetimeLocal(value) {
  const date = parseDate(value);
  if (!date) return '';
  const tzOffsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - tzOffsetMs).toISOString().slice(0, 16);
}

function fromDatetimeLocal(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function serializeForm(form) {
  const patch = draftEntryFor(form.dataset.recordId) || defaultDraftPatch(baseRecords.find(r => r.id === form.dataset.recordId));
  const fd = new FormData(form);
  patch.status = fd.get('status') || patch.status;
  patch.location = (fd.get('location') || '').trim() || null;
  patch.source_url = (fd.get('source_url') || '').trim() || null;
  const confidenceRaw = fd.get('confidence');
  patch.confidence = confidenceRaw === '' ? null : Number(confidenceRaw);
  patch.notes = (fd.get('notes') || '').trim();
  const deadlineRows = Array.from(form.querySelectorAll('.deadline-row')).map(row => {
    const kind = row.querySelector('[name="deadlineKind"]').value.trim();
    const value = fromDatetimeLocal(row.querySelector('[name="deadlineValue"]').value);
    if (!kind && !value) return null;
    return { kind: kind || 'deadline', value };
  }).filter(Boolean);
  patch.deadlines = deadlineRows;
  patch.checked_at = new Date().toISOString();
  return patch;
}

function exportPatch() {
  const payload = {
    exported_at: new Date().toISOString(),
    source: 'admin-page-local-review',
    records: Object.values(reviewDraft.records || {})
  };
  downloadJson(`review-patch-${timestampSlug()}.json`, payload);
}

function downloadSnapshot() {
  const payload = {
    exported_at: new Date().toISOString(),
    source: 'admin-page-merged-snapshot',
    records: mergedRecords()
  };
  downloadJson(`admin-snapshot-${timestampSlug()}.json`, payload);
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function timestampSlug() {
  return new Date().toISOString().replaceAll(':', '').replaceAll('.', '-');
}

async function importPatchFile(file) {
  const text = await file.text();
  const parsed = JSON.parse(text);
  const incoming = Array.isArray(parsed.records) ? parsed.records : [];
  // Imported patches simply replace local draft entries by id.
  incoming.forEach(entry => {
    if (!entry || !entry.id) return;
    reviewDraft.records[entry.id] = entry;
  });
  saveDraftToStorage();
  render(baseRecords);
}

function handleRowClick(event) {
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (!action) return;
  const row = event.target.closest('.admin-row');
  if (!row) return;
  const record = mergedRecords().find(r => r.id === row.dataset.recordId);
  if (!record) return;

  if (action === 'approve') setQuickStatus(record, 'confirmed');
  if (action === 'reject') setQuickStatus(record, 'scan_failed');
  if (action === 'discard-draft') removeDraftPatch(record);
  if (action === 'toggle-edit') {
    const details = row.querySelector('.edit-box');
    if (details) details.open = !details.open;
  }
  if (action === 'add-deadline') {
    const list = row.querySelector('.deadline-list');
    const div = document.createElement('div');
    div.className = 'deadline-row';
    div.innerHTML = `
      <input type="text" name="deadlineKind" value="deadline" placeholder="kind (e.g. abstract, paper)" />
      <input type="datetime-local" name="deadlineValue" value="" />
      <button type="button" class="btn tiny danger ghost" data-action="remove-deadline">Remove</button>
    `;
    list.appendChild(div);
  }
  if (action === 'remove-deadline') {
    event.target.closest('.deadline-row')?.remove();
  }
}

function handleFormSubmit(event) {
  const form = event.target.closest('.edit-form');
  if (!form) return;
  event.preventDefault();
  const patch = serializeForm(form);
  reviewDraft.records[patch.id] = patch;
  saveDraftToStorage();
  render(baseRecords);
}

function bindTopLevelActions() {
  document.getElementById('saveDraftBtn').addEventListener('click', () => saveDraftToStorage());
  document.getElementById('exportReviewsBtn').addEventListener('click', exportPatch);
  document.getElementById('downloadSnapshotBtn').addEventListener('click', downloadSnapshot);
  document.getElementById('clearDraftBtn').addEventListener('click', clearDraft);
  document.getElementById('importReviewsInput').addEventListener('change', async (event) => {
    const [file] = event.target.files || [];
    if (!file) return;
    await importPatchFile(file);
    event.target.value = '';
  });

  ['adminSearch','bucketFilter','parserFilter','statusFilter','scanEnabledOnly','activeOnly','previewOnly','editedOnly'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => render(baseRecords));
    document.getElementById(id).addEventListener('change', () => render(baseRecords));
  });

  document.body.addEventListener('click', handleRowClick);
  document.body.addEventListener('submit', handleFormSubmit);
}

async function bootAdminPage() {
  initThemeToggle();
  const ok = await verifyAdminPassword();
  if (!ok) {
    window.location.replace('./index.html');
    return;
  }

  const records = await loadAdminData();
  baseRecords = records;
  const statusFilter = document.getElementById('statusFilter');
  statusOptions(records).forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    statusFilter.appendChild(opt);
  });

  bindTopLevelActions();
  updateDraftStatus();
  render(baseRecords);
}

bootAdminPage();
