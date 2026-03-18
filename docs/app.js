async function loadData() {
  const paths = ['./assets/venues.json', './venues.json'];
  for (const path of paths) {
    try {
      const res = await fetch(path);
      if (res.ok) return await res.json();
    } catch (err) {}
  }
  return [];
}

function normalizeType(type) {
  if (!type) return '';
  const t = String(type).toLowerCase();
  if (t === 'symposium' || t === 'journal-track') return 'conference';
  return t;
}

function titleCase(s) {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function parseDate(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

function broadAreas(record) {
  const raw = (record.domain || []).map(x => String(x).toLowerCase());
  const out = new Set();

  raw.forEach(d => {
    if ([
      'ai', 'machine-learning', 'ml', 'nlp', 'vision', 'computer-vision',
      'data-mining', 'databases', 'db', 'ir', 'information-retrieval',
      'data', 'kdd'
    ].includes(d)) out.add('AI+Data');

    if ([
      'systems', 'networking', 'cloud', 'distributed-systems', 'architecture',
      'computer-architecture', 'operating-systems'
    ].includes(d)) out.add('Systems');

    if (['security', 'privacy', 'cryptography', 'crypto'].includes(d)) out.add('Security');

    if ([
      'software-engineering', 'se', 'programming-languages', 'pl',
      'theory', 'formal-methods', 'verification', 'compilers'
    ].includes(d)) out.add('SE+Theory');
  });

  if (!out.size) {
    if (raw.some(d => d.includes('security') || d.includes('privacy'))) out.add('Security');
    else if (raw.some(d => d.includes('system') || d.includes('network') || d.includes('architecture'))) out.add('Systems');
    else if (raw.some(d => d.includes('software') || d.includes('theory') || d.includes('language') || d.includes('formal'))) out.add('SE+Theory');
    else out.add('AI+Data');
  }

  return Array.from(out);
}

function areaHtml(areas) {
  return areas.map(a => `<span class="area-text area-${a.toLowerCase().replace(/[^a-z0-9]+/g, '-')}">${a}</span>`).join(' <span class="slash">/</span> ');
}

function findNextDeadline(record) {
  const items = (record.deadlines || [])
    .map(d => ({ ...d, date: parseDate(d.value) }))
    .filter(d => d.date)
    .sort((a, b) => a.date - b.date);

  const now = new Date();
  const upcoming = items.find(d => d.date > now);
  return upcoming || items[0] || null;
}

function formatCountdown(date) {
  if (!date) return '';
  const now = new Date();
  let diff = date.getTime() - now.getTime();
  const passed = diff <= 0;
  diff = Math.abs(diff);

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  diff -= days * (1000 * 60 * 60 * 24);
  const hours = Math.floor(diff / (1000 * 60 * 60));
  diff -= hours * (1000 * 60 * 60);
  const mins = Math.floor(diff / (1000 * 60));

  return passed ? `${days}d ${hours}h ago` : `${days}d ${hours}h ${mins}m left`;
}

function computeStatus(record, nextDeadline) {
  if (!nextDeadline || !nextDeadline.date) return { label: 'Not announced', cls: 'not-announced' };
  const diff = nextDeadline.date.getTime() - Date.now();
  if (diff <= 0) return { label: 'Passed', cls: 'passed' };
  const days = diff / (1000 * 60 * 60 * 24);
  if (days < 3) return { label: 'Urgent', cls: 'urgent' };
  if (days < 7) return { label: 'Soon', cls: 'soon' };
  return { label: 'Upcoming', cls: 'upcoming' };
}

function formatDeadlinePrimary(record, nextDeadline) {
  if (!nextDeadline || !nextDeadline.date) return 'Deadline not announced';
  const kind = titleCase(nextDeadline.kind || 'Deadline');
  return `${kind}: ${nextDeadline.date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`;
}

function formatDeadlineSecondary(record, nextDeadline) {
  if (!nextDeadline || !nextDeadline.date) return sourceLine(record);
  const countdown = formatCountdown(nextDeadline.date);
  const src = sourceLine(record);
  return `${countdown}${src ? ' · ' + src : ''}`;
}

function sourceLine(record) {
  const bits = [];
  if (record.source_type) bits.push(record.source_type);
  if (typeof record.confidence === 'number') bits.push(`confidence ${record.confidence.toFixed(2)}`);
  return bits.join(' · ');
}

function locationText(record) {
  if (record.location) return record.location;
  if (record.place) return record.place;
  return 'Location TBD';
}

function searchHaystack(record, areas) {
  return [
    record.title,
    record.short_name,
    ...(record.aliases || []),
    ...(record.domain || []),
    ...areas
  ].join(' ').toLowerCase();
}

function compareRecords(mode) {
  return (a, b) => {
    const aNext = findNextDeadline(a);
    const bNext = findNextDeadline(b);
    const aTime = aNext?.date ? aNext.date.getTime() : Infinity;
    const bTime = bNext?.date ? bNext.date.getTime() : Infinity;

    if (mode === 'latest') return bTime - aTime;
    if (mode === 'az') return `${a.short_name} ${a.title}`.localeCompare(`${b.short_name} ${b.title}`);
    if (mode === 'tier') {
      const order = { top: 0, strong: 1, mid: 2, workshop: 3, fast: 4 };
      return (order[a.tier] ?? 99) - (order[b.tier] ?? 99) || aTime - bTime;
    }
    return aTime - bTime;
  };
}

function applyFilters(records) {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const selectedArea = document.querySelector('.area-btn.active')?.dataset.area || '';
  const type = document.getElementById('typeFilter').value;
  const tier = document.getElementById('tierFilter').value;
  const scan = document.getElementById('scanFilter').value;
  const topOnly = document.getElementById('topOnly').checked;

  return records.filter(r => {
    const areas = broadAreas(r);
    const hay = searchHaystack(r, areas);
    if (q && !hay.includes(q)) return false;
    if (selectedArea && !areas.includes(selectedArea)) return false;
    if (type && normalizeType(r.type) !== type) return false;
    if (tier && r.tier !== tier) return false;
    if (scan === 'enabled' && !r.scan_enabled) return false;
    if (scan === 'catalog' && r.scan_enabled) return false;
    if (topOnly && r.tier !== 'top') return false;
    return true;
  });
}

function render(records) {
  const list = document.getElementById('list');
  const tpl = document.getElementById('rowTemplate');
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
    const areas = broadAreas(r);
    const nextDeadline = findNextDeadline(r);
    const status = computeStatus(r, nextDeadline);

    node.querySelector('.tier').textContent = titleCase(r.tier || 'Catalog');
    node.querySelector('.type').textContent = titleCase(normalizeType(r.type) || 'Venue');

    const scanEl = node.querySelector('.scan-state');
    scanEl.textContent = r.scan_enabled ? 'Scan enabled' : 'Catalog only';
    scanEl.classList.toggle('scan-on', !!r.scan_enabled);

    node.querySelector('.areas').innerHTML = areaHtml(areas);
    node.querySelector('.year').textContent = `Year ${r.year || 'TBD'}`;
    node.querySelector('.location').textContent = locationText(r);

    node.querySelector('.title').textContent = `${r.short_name || ''}${r.short_name && r.title ? ' — ' : ''}${r.title || ''}`;

    const venueLink = node.querySelector('.venue-link');
    venueLink.href = r.website || '#';
    const cfpLink = node.querySelector('.cfp-link');
    cfpLink.href = r.cfp_url || r.website || '#';

    const statusChip = node.querySelector('.status-chip');
    statusChip.textContent = status.label;
    statusChip.classList.add(status.cls);

    node.querySelector('.deadline-primary').textContent = formatDeadlinePrimary(r, nextDeadline);
    node.querySelector('.deadline-secondary').textContent = formatDeadlineSecondary(r, nextDeadline);

    list.appendChild(node);
  });
}

loadData().then(records => {
  const sortMode = 'nearest';

  function rerender() {
    const filtered = applyFilters(records).sort(compareRecords(sortMode));
    render(filtered);
  }

  ['search', 'typeFilter', 'tierFilter', 'scanFilter', 'topOnly'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('input', rerender);
    el.addEventListener('change', rerender);
  });

  document.querySelectorAll('.area-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.area-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      rerender();
    });
  });

  rerender();
});
