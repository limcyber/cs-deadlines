async function loadData() {
  const res = await fetch('./assets/venues.json');
  return await res.json();
}

const BROAD_AREAS = [
  'AI+Data',
  'Systems',
  'Security',
  'SE+Theory'
];

const DOMAIN_TO_AREA = {
  agents: 'AI+Data',
  ai: 'AI+Data',
  bioinformatics: 'AI+Data',
  data: 'AI+Data',
  'data-mining': 'AI+Data',
  db: 'AI+Data',
  graphics: 'AI+Data',
  ir: 'AI+Data',
  ml: 'AI+Data',
  nlp: 'AI+Data',
  robotics: 'AI+Data',
  speech: 'AI+Data',
  statistics: 'AI+Data',
  vision: 'AI+Data',
  visualization: 'AI+Data',

  architecture: 'Systems',
  cloud: 'Systems',
  hardware: 'Systems',
  hpc: 'Systems',
  networking: 'Systems',
  storage: 'Systems',
  systems: 'Systems',
  web: 'Systems',

  crypto: 'Security',
  privacy: 'Security',
  security: 'Security',

  education: 'SE+Theory',
  hci: 'SE+Theory',
  optimization: 'SE+Theory',
  pl: 'SE+Theory',
  software: 'SE+Theory',
  theory: 'SE+Theory'
};

function normalizeType(type) {
  // The UI now uses only two type buckets:
  // 1) "conference" (also absorbs symposium and journal-track)
  // 2) "workshop"
  return type === 'workshop' ? 'workshop' : 'conference';
}

function getBroadAreas(record) {
  const rawDomains = Array.isArray(record.domain) ? record.domain : [];
  const mapped = rawDomains
    .map(domain => DOMAIN_TO_AREA[domain] || 'Systems');

  return Array.from(new Set(mapped));
}

function enrichRecords(records) {
  return records.map(record => ({
    ...record,
    broadAreas: getBroadAreas(record),
    displayType: normalizeType(record.type)
  }));
}

function formatDeadlines(deadlines) {
  if (!deadlines || !deadlines.length) return 'No confirmed deadlines yet';

  const ul = document.createElement('ul');

  deadlines.forEach(deadline => {
    const li = document.createElement('li');
    li.textContent = `${deadline.kind}: ${deadline.value}`;
    ul.appendChild(li);
  });

  return ul;
}

function formatVenue(record) {
  const parts = [];

  if (record.location) parts.push(record.location);

  if (record.venue_date_start || record.venue_date_end) {
    parts.push([record.venue_date_start, record.venue_date_end].filter(Boolean).join(' → '));
  }

  return parts.length ? parts.join(' · ') : 'Venue details not added yet';
}

function render(records) {
  const list = document.getElementById('list');
  const template = document.getElementById('cardTemplate');
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

  records.forEach(record => {
    const node = template.content.cloneNode(true);

    node.querySelector('.tier').textContent = record.tier;
    node.querySelector('.type').textContent = record.displayType;

    const scanState = node.querySelector('.scan-state');
    scanState.textContent = record.scan_enabled ? 'scan enabled' : 'catalog only';
    if (record.scan_enabled) scanState.classList.add('scan-on');

    node.querySelector('.title').textContent = `${record.short_name} — ${record.title}`;
    node.querySelector('.domains').textContent = `Areas: ${record.broadAreas.join(', ')}`;
    node.querySelector('.year').textContent = `${record.year}`;
    node.querySelector('.status').textContent = record.status || 'catalog_seed';
    node.querySelector('.confidence').textContent = `${(record.confidence ?? 0).toFixed(2)}`;
    node.querySelector('.location').textContent = formatVenue(record);
    node.querySelector('.notes').textContent = record.notes || 'No notes yet.';

    const deadlinesHost = node.querySelector('.deadlines');
    const deadlineContent = formatDeadlines(record.deadlines);
    if (typeof deadlineContent === 'string') {
      deadlinesHost.textContent = deadlineContent;
    } else {
      deadlinesHost.appendChild(deadlineContent);
    }

    const preview = node.querySelector('.preview');
    const previewLines = (record.scan_preview || []).slice(0, 3);

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

    node.querySelector('.links').innerHTML =
      `<a href="${record.website}" target="_blank" rel="noopener">venue link</a> · ` +
      `<a href="${record.cfp_url}" target="_blank" rel="noopener">catalog / CFP link</a>`;

    list.appendChild(node);
  });
}

function applyFilters(records) {
  const query = document.getElementById('search').value.trim().toLowerCase();
  const area = document.getElementById('domainFilter').value;
  const type = document.getElementById('typeFilter').value;
  const tier = document.getElementById('tierFilter').value;
  const scan = document.getElementById('scanFilter').value;

  return records.filter(record => {
    const searchableText = [
      record.title,
      record.short_name,
      ...(record.aliases || []),
      ...(record.domain || []),
      ...(record.broadAreas || [])
    ].join(' ').toLowerCase();

    if (query && !searchableText.includes(query)) return false;
    if (area && !(record.broadAreas || []).includes(area)) return false;
    if (type && record.displayType !== type) return false;
    if (tier && record.tier !== tier) return false;
    if (scan === 'enabled' && !record.scan_enabled) return false;
    if (scan === 'catalog' && record.scan_enabled) return false;

    return true;
  });
}

loadData().then(rawRecords => {
  const records = enrichRecords(rawRecords);
  const domainFilter = document.getElementById('domainFilter');

  BROAD_AREAS.forEach(area => {
    const option = document.createElement('option');
    option.value = area;
    option.textContent = area;
    domainFilter.appendChild(option);
  });

  const rerender = () => render(applyFilters(records));

  ['search', 'domainFilter', 'typeFilter', 'tierFilter', 'scanFilter'].forEach(id => {
    document.getElementById(id).addEventListener('input', rerender);
    document.getElementById(id).addEventListener('change', rerender);
  });

  rerender();
});
