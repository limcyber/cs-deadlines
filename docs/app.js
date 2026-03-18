async function loadData() {
  const res = await fetch('./assets/venues.json');
  return await res.json();
}

function uniqueValues(records, key) {
  const values = new Set();
  records.forEach(r => {
    const value = r[key];
    if (Array.isArray(value)) value.forEach(v => values.add(v));
    else if (value) values.add(value);
  });
  return Array.from(values).filter(Boolean).sort();
}

function formatDeadlines(deadlines) {
  if (!deadlines || !deadlines.length) return 'No confirmed deadlines yet';
  const ul = document.createElement('ul');
  deadlines.forEach(d => {
    const li = document.createElement('li');
    li.textContent = `${d.kind}: ${d.value}`;
    ul.appendChild(li);
  });
  return ul;
}

function formatVenue(r) {
  const parts = [];
  if (r.location) parts.push(r.location);
  if (r.venue_date_start || r.venue_date_end) {
    parts.push([r.venue_date_start, r.venue_date_end].filter(Boolean).join(' → '));
  }
  return parts.length ? parts.join(' · ') : 'Venue details not added yet';
}

function render(records) {
  const list = document.getElementById('list');
  const tpl = document.getElementById('cardTemplate');
  const resultCount = document.getElementById('resultCount');
  list.innerHTML = '';
  resultCount.textContent = records.length;

  if (!records.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No venues match the current filters.';
    list.appendChild(empty);
    return;
  }

  records.forEach(r => {
    const node = tpl.content.cloneNode(true);
    node.querySelector('.tier').textContent = r.tier;
    node.querySelector('.type').textContent = r.type;
    const scanState = node.querySelector('.scan-state');
    scanState.textContent = r.scan_enabled ? 'scan enabled' : 'catalog only';
    if (r.scan_enabled) scanState.classList.add('scan-on');

    node.querySelector('.title').textContent = `${r.short_name} — ${r.title}`;
    node.querySelector('.domains').textContent = `Domains: ${(r.domain || []).join(', ')}`;
    node.querySelector('.year').textContent = `${r.year}`;
    node.querySelector('.status').textContent = r.status || 'catalog_seed';
    node.querySelector('.confidence').textContent = `${(r.confidence ?? 0).toFixed(2)}`;
    node.querySelector('.location').textContent = formatVenue(r);
    node.querySelector('.notes').textContent = r.notes || 'No notes yet.';

    const deadlinesHost = node.querySelector('.deadlines');
    const deadlineContent = formatDeadlines(r.deadlines);
    if (typeof deadlineContent === 'string') deadlinesHost.textContent = deadlineContent;
    else deadlinesHost.appendChild(deadlineContent);

    const preview = node.querySelector('.preview');
    const previewLines = (r.scan_preview || []).slice(0, 3);
    if (previewLines.length) {
      previewLines.forEach(line => {
        const p = document.createElement('p');
        p.textContent = line;
        preview.appendChild(p);
      });
    } else {
      preview.textContent = 'No scan preview available.';
      preview.classList.add('notes');
    }

    node.querySelector('.links').innerHTML = `<a href="${r.website}" target="_blank" rel="noopener">venue link</a> · <a href="${r.cfp_url}" target="_blank" rel="noopener">catalog / CFP link</a>`;
    list.appendChild(node);
  });
}

function applyFilters(records) {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const domain = document.getElementById('domainFilter').value;
  const type = document.getElementById('typeFilter').value;
  const tier = document.getElementById('tierFilter').value;
  const scan = document.getElementById('scanFilter').value;

  return records.filter(r => {
    const hay = [r.title, r.short_name, ...(r.aliases || []), ...(r.domain || [])].join(' ').toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (domain && !(r.domain || []).includes(domain)) return false;
    if (type && r.type !== type) return false;
    if (tier && r.tier !== tier) return false;
    if (scan === 'enabled' && !r.scan_enabled) return false;
    if (scan === 'catalog' && r.scan_enabled) return false;
    return true;
  });
}

loadData().then(records => {
  const domainFilter = document.getElementById('domainFilter');
  uniqueValues(records, 'domain').forEach(v => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    domainFilter.appendChild(opt);
  });

  const rerender = () => render(applyFilters(records));
  ['search', 'domainFilter', 'typeFilter', 'tierFilter', 'scanFilter'].forEach(id => {
    document.getElementById(id).addEventListener('input', rerender);
    document.getElementById(id).addEventListener('change', rerender);
  });
  rerender();
});
