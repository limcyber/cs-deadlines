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

function bucketFor(record) {
  const s = norm(record.status);
  if (s === 'confirmed' || s === 'closed') return 'confirmed';
  if (['scanned', 'scan_failed', 'review_required', 'conflict'].includes(s)) return 'review';
  if (s === 'scan_failed') return 'failed';
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
  });
  if (!out.size) out.add('AI+Data');
  return Array.from(out).join(' / ');
}

function parseDate(v) {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

function nextDeadline(record) {
  const items = (record.deadlines || []).map(d => ({...d, date: parseDate(d.value)})).filter(d => d.date).sort((a,b)=>a.date-b.date);
  const now = Date.now();
  return items.find(d => d.date.getTime() > now) || items[0] || null;
}

function formatWhen(value) {
  const d = parseDate(value);
  return d ? d.toLocaleString() : '—';
}

function haystack(record) {
  return [
    record.title,
    record.short_name,
    ...(record.aliases || []),
    ...(record.domain || []),
    record.parser,
    record.notes,
    record.source_url,
    record.status,
    areas(record)
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

  if (q && !haystack(record).includes(q)) return false;
  if (bucket && effectiveBucket(record) !== bucket) return false;
  if (parser && record.parser !== parser) return false;
  if (status && record.status !== status) return false;
  if (scanEnabledOnly && !record.scan_enabled) return false;
  if (activeOnly && record.active === false) return false;
  return true;
}

function summaryCounts(records) {
  const counts = { total: records.length, confirmed: 0, review: 0, catalog: 0, failed: 0 };
  records.forEach(r => counts[effectiveBucket(r)] = (counts[effectiveBucket(r)] || 0) + 1);
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
    `<span class="badge scan">${record.scan_enabled ? 'scan enabled' : 'catalog only'}</span>`
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
    node.querySelector('.admin-title').textContent = `${record.short_name} — ${record.title}`;
    node.querySelector('.admin-meta').textContent = `${areas(record)} · ${record.year || '—'} · ${record.location || 'Location TBD'} · confidence ${confidenceText(record)}`;
    node.querySelector('.admin-badges').innerHTML = createBadges(record);
    const nd = nextDeadline(record);
    node.querySelector('.admin-deadline').textContent = nd ? `${nd.kind || 'deadline'}: ${formatWhen(nd.value)}` : 'No structured deadline available';
    node.querySelector('.admin-links').innerHTML = [
      record.website ? `<a href="${record.website}" target="_blank" rel="noopener">Venue</a>` : '',
      record.cfp_url ? `<a href="${record.cfp_url}" target="_blank" rel="noopener">CFP</a>` : '',
      record.source_url ? `<a href="${record.source_url}" target="_blank" rel="noopener">Source</a>` : ''
    ].filter(Boolean).join(' <span class="dot">·</span> ');
    node.querySelector('.detail-notes').textContent = record.notes || '—';
    const preview = (record.scan_preview || []).length ? `<ul>${record.scan_preview.map(x => `<li>${x}</li>`).join('')}</ul>` : '—';
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
      <td><strong>${record.short_name}</strong><br><span class="table-sub">${record.title}</span></td>
      <td>${effectiveBucket(record)}</td>
      <td>${record.status || '—'}</td>
      <td>${record.parser || '—'}</td>
      <td>${record.scan_enabled ? 'enabled' : 'catalog'}</td>
      <td>${confidenceText(record)}</td>
      <td>${record.checked_at ? formatWhen(record.checked_at) : '—'}</td>
      <td>${record.source_url ? `<a href="${record.source_url}" target="_blank" rel="noopener">open</a>` : '—'}</td>
    `;
    tbody.appendChild(tr);
  });
}

function sortRecords(records) {
  return records.slice().sort((a, b) => {
    const order = { review: 0, failed: 1, confirmed: 2, catalog: 3 };
    return (order[effectiveBucket(a)] ?? 9) - (order[effectiveBucket(b)] ?? 9)
      || String(a.short_name || '').localeCompare(String(b.short_name || ''));
  });
}

function render(records) {
  const filtered = sortRecords(records.filter(passesFilters));
  renderSummary(filtered);
  renderList('reviewQueue', filtered.filter(r => ['review','failed'].includes(effectiveBucket(r))));
  renderList('catalogSeeds', filtered.filter(r => effectiveBucket(r) === 'catalog'));
  renderList('scanFailures', filtered.filter(r => effectiveBucket(r) === 'failed'));
  renderTable(filtered);
}

loadAdminData().then(records => {
  const statusFilter = document.getElementById('statusFilter');
  statusOptions(records).forEach(s => {
    const opt = document.createElement('option');
    opt.value = s;
    opt.textContent = s;
    statusFilter.appendChild(opt);
  });

  ['adminSearch','bucketFilter','parserFilter','statusFilter','scanEnabledOnly','activeOnly'].forEach(id => {
    document.getElementById(id).addEventListener('input', () => render(records));
    document.getElementById(id).addEventListener('change', () => render(records));
  });

  render(records);
});
