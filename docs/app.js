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

const THEME_STORAGE_KEY = 'cs-deadlines-theme-v1';
const LAYOUT_MQ = window.matchMedia('(max-width: 760px)');

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

function applyTheme(theme) {
  // The public page supports two curated themes without changing the data model.
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

function applyLayoutMode(isMobile) {
  const mode = isMobile ? 'mobile' : 'desktop';
  document.body.dataset.layout = mode;
  const chip = document.getElementById('layoutChip');
  if (chip) chip.textContent = isMobile ? 'Premium mobile layout' : 'Desktop layout';
}

function initLayoutMode() {
  applyLayoutMode(!!LAYOUT_MQ.matches);
  const onChange = event => applyLayoutMode(!!event.matches);
  if (typeof LAYOUT_MQ.addEventListener === 'function') {
    LAYOUT_MQ.addEventListener('change', onChange);
  } else if (typeof LAYOUT_MQ.addListener === 'function') {
    LAYOUT_MQ.addListener(onChange);
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
    // Only allow explicit web links to prevent javascript: style injections.
    if (u.protocol === 'http:' || u.protocol === 'https:') return u.href;
    return null;
  } catch (err) {
    return null;
  }
}

function setSafeAnchor(anchor, candidateUrl) {
  const safe = sanitizeHttpUrl(candidateUrl);
  if (safe) {
    anchor.href = safe;
    anchor.target = '_blank';
    anchor.rel = 'noopener';
    anchor.removeAttribute('aria-disabled');
    anchor.classList.remove('disabled-link');
    return;
  }
  anchor.removeAttribute('href');
  anchor.removeAttribute('target');
  anchor.removeAttribute('rel');
  anchor.setAttribute('aria-disabled', 'true');
  anchor.classList.add('disabled-link');
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
  // Convert many venue-specific domain labels into a smaller set of browsing buckets.
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

function isPlausibleYear(date, conferenceYear, allowFullPrevYear = false) {
  if (!conferenceYear) return true;
  const y = date.getUTCFullYear();
  const m = date.getUTCMonth() + 1;
  if (y === conferenceYear) return true;
  // Many CFP deadlines for year N happen in late year N-1.
  if (y === conferenceYear - 1 && m >= 8) return true;
  if (allowFullPrevYear && y === conferenceYear - 1) return true;
  return false;
}

function looksLikeNoiseLine(text) {
  const t = String(text || '').toLowerCase();
  return [
    'retrieved on',
    'curated by',
    'update ',
    'copyright',
  ].some(x => t.includes(x));
}

function parsedPreviewSource(record) {
  if (!record.scan_enabled) return [];
  if (!['scanned', 'review_required'].includes(String(record.status || '').toLowerCase())) return [];

  const conferenceYear = Number(record.year || 0);
  // Scanner previews stay behind confidence/noise filters so public cards remain readable.
  return (record.parsed_deadlines || [])
    .map(d => ({
      kind: d.kind,
      value: d.value,
      raw_text: d.raw_text,
      confidence: Number(d.confidence || 0),
      date: parseDate(d.value),
      year_fallback: !!d.year_fallback,
      isPreview: true
    }))
    .filter(d => d.date)
    .filter(d => d.confidence >= 0.45)
    .filter(d => !looksLikeNoiseLine(d.raw_text))
    .filter(d => isPlausibleYear(d.date, conferenceYear, d.year_fallback));
}

function findNextDeadline(record) {
  // Prefer confirmed deadlines, then fall back to parsed preview candidates for visibility.
  const source = (record.deadlines && record.deadlines.length)
    ? record.deadlines.map(d => ({ ...d, isPreview: false }))
    : parsedPreviewSource(record);

  const items = source
    .map(d => ({ ...d, date: d.date || parseDate(d.value) }))
    .filter(d => d.date instanceof Date)
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
  return `${kind}: ${nextDeadline.date.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`;
}

function formatDeadlineSecondary(record, nextDeadline) {
  if (!nextDeadline || !nextDeadline.date) return sourceLine(record);
  const countdown = formatCountdown(nextDeadline.date);
  const preview = nextDeadline.isPreview ? 'unconfirmed preview' : '';
  const src = sourceLine(record);
  return `${countdown}${preview ? ' · ' + preview : ''}${src ? ' · ' + src : ''}`;
}

function sourceLine(record) {
  const bits = [];
  if (record.source_type) bits.push(record.source_type);
  if (typeof record.confidence === 'number') bits.push(`confidence ${record.confidence.toFixed(2)}`);
  return bits.join(' · ');
}

function isPlausibleLocation(value) {
  const text = String(value || '').trim();
  if (!text) return false;
  const lower = text.toLowerCase();
  if (text.length < 4 || text.length > 48) return false;
  if (/[0-9]/.test(text)) return false;
  if (text.split(',').length > 3) return false;
  if (['tbd', 'online', 'virtual', 'conference', 'symposium', 'heart of'].some(x => lower.includes(x))) return false;
  if (lower === 'person' || lower.startsWith('person ')) return false;
  if (lower.startsWith('person in ') || lower.startsWith('person at ')) return false;
  if (/^the\s+st\.?$/i.test(text)) return false;
  return true;
}

function locationText(record) {
  if (isPlausibleLocation(record.location)) return record.location;
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
    const aHasDeadline = !!aNext?.date;
    const bHasDeadline = !!bNext?.date;

    const aTime = aHasDeadline ? aNext.date.getTime() : Infinity;
    const bTime = bHasDeadline ? bNext.date.getTime() : Infinity;
    const now = Date.now();

    if (mode === 'nearest') {
      const aUpcoming = aHasDeadline && aTime > now;
      const bUpcoming = bHasDeadline && bTime > now;

      // "Nearest" is tuned for deadline triage rather than strict chronological sorting.
      if (aUpcoming !== bUpcoming) return aUpcoming ? -1 : 1;
      if (aUpcoming && bUpcoming) return aTime - bTime;

      // After upcoming items, keep passed deadlines above "not announced".
      if (aHasDeadline !== bHasDeadline) return aHasDeadline ? -1 : 1;
      if (aHasDeadline && bHasDeadline) return bTime - aTime;
      return `${a.short_name} ${a.title}`.localeCompare(`${b.short_name} ${b.title}`);
    }

    // Non-nearest modes: always keep "Deadline not announced" at the bottom.
    if (aHasDeadline !== bHasDeadline) return aHasDeadline ? -1 : 1;

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

  return records.filter(r => {
    const areas = broadAreas(r);
    const hay = searchHaystack(r, areas);
    if (q && !hay.includes(q)) return false;
    if (selectedArea && !areas.includes(selectedArea)) return false;
    if (type && normalizeType(r.type) !== type) return false;
    if (tier && r.tier !== tier) return false;
    if (scan === 'enabled' && !r.scan_enabled) return false;
    if (scan === 'catalog' && r.scan_enabled) return false;
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
    setSafeAnchor(venueLink, r.website);
    const cfpLink = node.querySelector('.cfp-link');
    setSafeAnchor(cfpLink, r.cfp_url || r.website);

    const statusChip = node.querySelector('.status-chip');
    statusChip.textContent = status.label;
    statusChip.classList.add(status.cls);

    node.querySelector('.deadline-primary').textContent = formatDeadlinePrimary(r, nextDeadline);
    node.querySelector('.deadline-secondary').textContent = formatDeadlineSecondary(r, nextDeadline);

    list.appendChild(node);
  });
}

initThemeToggle();
initLayoutMode();

loadData().then(records => {
  function rerender() {
    const sortMode = document.getElementById('sortFilter').value || 'nearest';
    const filtered = applyFilters(records).sort(compareRecords(sortMode));
    render(filtered);
  }

  ['sortFilter', 'search', 'typeFilter', 'tierFilter', 'scanFilter'].forEach(id => {
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
