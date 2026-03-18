const DATA_URL = 'assets/venues.json';
const SUMMARY_URL = 'assets/build-summary.json';
const AREA_CLASS = {
  'AI+Data': 'area-ai-data',
  Systems: 'area-systems',
  Security: 'area-security',
  'SE+Theory': 'area-se-theory'
};

const TYPE_LABEL = {
  conference: 'Conference',
  workshop: 'Workshop'
};

function titleCase(value) {
  return (value || '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function parseDate(value) {
  if (!value) return null;
  const dt = new Date(String(value).trim());
  return Number.isNaN(dt.getTime()) ? null : dt;
}

async function loadJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Failed to load ${url}`);
  return response.json();
}

async function loadAll() {
  const [records, summary] = await Promise.all([loadJson(DATA_URL), loadJson(SUMMARY_URL)]);
  return { records, summary };
}

function searchMatch(record, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  const hay = [
    record.title,
    record.short_name,
    ...(record.aliases || []),
    ...(record.search_tokens || []),
    ...(record.domain || []),
    ...(record.areas || [])
  ].join(' ').toLowerCase();
  return hay.includes(q);
}

function nextDeadline(record) {
  return record.next_deadline || null;
}

function nextDate(record) {
  const next = nextDeadline(record);
  return next?.value ? parseDate(next.value) : null;
}

function remainingText(dt) {
  if (!dt) return '';
  const diff = dt.getTime() - Date.now();
  if (diff <= 0) return 'Deadline passed';
  const totalMinutes = Math.floor(diff / 60000);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  return `${days}d ${hours}h ${minutes}m left`;
}

function statusFor(record) {
  if (record.review_required) return { label: 'Review required', cls: 'review' };
  const dt = nextDate(record);
  if (!dt) return { label: 'Not announced', cls: 'not-announced' };
  const diff = dt.getTime() - Date.now();
  if (diff <= 0) return { label: 'Passed', cls: 'passed' };
  const hours = diff / 36e5;
  if (hours <= 72) return { label: 'Urgent', cls: 'urgent' };
  if (hours <= 168) return { label: 'Soon', cls: 'soon' };
  return { label: 'Upcoming', cls: 'upcoming' };
}

function formatAbsolute(dt, timezoneLabel) {
  if (!dt) return 'Not announced';
  return `${dt.toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })}${timezoneLabel ? ` (${timezoneLabel})` : ''}`;
}

function localText(dt) {
  if (!dt) return '';
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return `${dt.toLocaleString([], { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })} (${tz})`;
}

function timelineText(record) {
  const deadlines = record.public_deadlines || [];
  if (!deadlines.length) return '';
  return deadlines.map(d => `${titleCase(d.kind)}: ${formatAbsolute(parseDate(d.value), d.timezone)}`).join(' · ');
}

function extensionText(next) {
  if (!next) return '';
  const previous = next.extended_from || next.previous_value || next.original_value;
  if (!previous) return '';
  return `Extension history: previously ${formatAbsolute(parseDate(previous), next.timezone)}`;
}

function scanBadgeText(record) {
  if (record.scan_status === 'confirmed') return 'Confirmed';
  if (record.scan_enabled) return 'Scanned';
  return 'Catalog';
}

function compareRecords(mode) {
  return (a, b) => {
    const aDt = nextDate(a);
    const bDt = nextDate(b);
    const aTime = aDt ? aDt.getTime() : Number.POSITIVE_INFINITY;
    const bTime = bDt ? bDt.getTime() : Number.POSITIVE_INFINITY;
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
  const query = document.getElementById('search').value.trim();
  const selectedArea = document.querySelector('.area-btn.active')?.dataset.area || '';
  const type = document.getElementById('typeFilter').value;
  const topOnly = document.getElementById('topOnly').checked;
  return records.filter(record => {
    if (!searchMatch(record, query)) return false;
    if (selectedArea && !(record.areas || []).includes(selectedArea)) return false;
    if (type && record.type !== type) return false;
    if (topOnly && record.tier !== 'top') return false;
    return true;
  });
}

function googleCalendarUrl(record, next) {
  if (!next?.value) return null;
  const start = parseDate(next.value);
  if (!start) return null;
  const end = new Date(start.getTime() + 30 * 60000);
  const fmt = dt => dt.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: `${record.short_name} ${titleCase(next.kind)} deadline`,
    dates: `${fmt(start)}/${fmt(end)}`,
    details: `Source: ${record.source_url || record.cfp_url || record.website}`,
    location: record.location || ''
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function icsDataUrl(record, next) {
  if (!next?.value) return null;
  const start = parseDate(next.value);
  if (!start) return null;
  const end = new Date(start.getTime() + 30 * 60000);
  const fmt = dt => dt.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const ics = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'BEGIN:VEVENT',
    `UID:${record.id}-${next.kind}@cs-deadlines`,
    `DTSTAMP:${fmt(new Date())}`,
    `DTSTART:${fmt(start)}`,
    `DTEND:${fmt(end)}`,
    `SUMMARY:${record.short_name} ${titleCase(next.kind)} deadline`,
    `DESCRIPTION:Source ${record.source_url || record.cfp_url || record.website}`,
    'END:VEVENT',
    'END:VCALENDAR'
  ].join('\r\n');
  return `data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}`;
}

function renderAreaInline(areas) {
  return (areas || []).map(area => `<span class="area-inline ${AREA_CLASS[area] || ''}">${area}</span>`).join(' <span class="slash">/</span> ');
}

function render(records, summary) {
  const list = document.getElementById('list');
  const template = document.getElementById('rowTemplate');
  const resultCount = document.getElementById('resultCount');
  const buildMeta = document.getElementById('buildMeta');
  list.innerHTML = '';
  resultCount.textContent = records.length;
  if (summary?.generated_at) {
    buildMeta.textContent = `Build: ${new Date(summary.generated_at).toLocaleString()}`;
  }

  if (!records.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No venues match the current filters.';
    list.appendChild(empty);
    return;
  }

  records.forEach(record => {
    const fragment = template.content.cloneNode(true);
    const status = statusFor(record);
    const next = nextDeadline(record);
    const nextDt = nextDate(record);

    fragment.querySelector('.tier-badge').textContent = titleCase(record.tier);
    fragment.querySelector('.type-badge').textContent = TYPE_LABEL[record.type] || titleCase(record.type);
    fragment.querySelector('.scan-badge').textContent = scanBadgeText(record);
    const reviewBadge = fragment.querySelector('.review-badge');
    if (record.review_required) reviewBadge.classList.remove('hidden');

    fragment.querySelector('.areas-inline').innerHTML = renderAreaInline(record.areas);
    fragment.querySelector('.year-inline').textContent = String(record.year || 'TBD');
    fragment.querySelector('.location-inline').textContent = record.location || 'Location TBD';

    fragment.querySelector('.title').textContent = `${record.short_name}${record.title ? ' — ' + record.title : ''}`;
    fragment.querySelector('.venue-link').href = record.website || '#';
    fragment.querySelector('.cfp-link').href = record.cfp_url || record.website || '#';
    fragment.querySelector('.source-link').href = record.source_url || record.cfp_url || record.website || '#';

    const timelineLine = fragment.querySelector('.timeline-line');
    const timeline = timelineText(record);
    if (timeline) {
      timelineLine.classList.remove('hidden');
      timelineLine.textContent = timeline;
    }

    const extensionLine = fragment.querySelector('.extension-line');
    const extension = extensionText(next);
    if (extension) {
      extensionLine.classList.remove('hidden');
      extensionLine.textContent = extension;
    }

    const reviewLine = fragment.querySelector('.review-line');
    if (record.review_required && record.conflict_reason) {
      reviewLine.classList.remove('hidden');
      reviewLine.textContent = record.conflict_reason;
    }

    const statusChip = fragment.querySelector('.status-chip');
    statusChip.textContent = status.label;
    statusChip.classList.add(status.cls);

    fragment.querySelector('.deadline-primary').textContent = next
      ? `Next: ${titleCase(next.kind)} · ${remainingText(nextDt)}`
      : 'Next: Not announced';
    fragment.querySelector('.deadline-secondary').textContent = next
      ? `${formatAbsolute(nextDt, next.timezone)} · Your time: ${localText(nextDt)}`
      : 'Confirmed deadline is not available yet.';

    fragment.querySelector('.source-meta').textContent = `Source: ${record.source_display || 'pending'} · Confidence: ${titleCase(record.confidence)}${record.checked_at ? ` · Checked: ${new Date(record.checked_at).toLocaleString()}` : ''}`;

    const actionsLine = fragment.querySelector('.actions-line');
    const links = [`<a href="${record.website}" target="_blank" rel="noreferrer">Venue</a>`];
    const gcal = googleCalendarUrl(record, next);
    const ics = icsDataUrl(record, next);
    if (gcal) links.push(`<a href="${gcal}" target="_blank" rel="noreferrer">Google Calendar</a>`);
    if (ics) links.push(`<a href="${ics}" download="${record.id}-${next.kind || 'deadline'}.ics">ICS</a>`);
    actionsLine.innerHTML = links.join('<span class="slash">/</span>');

    list.appendChild(fragment);
  });
}

loadAll().then(({ records, summary }) => {
  function rerender() {
    const sortMode = document.getElementById('sortFilter').value;
    const filtered = applyFilters(records).sort(compareRecords(sortMode));
    render(filtered, summary);
  }

  ['search', 'typeFilter', 'sortFilter', 'topOnly'].forEach(id => {
    const element = document.getElementById(id);
    element.addEventListener('input', rerender);
    element.addEventListener('change', rerender);
  });

  document.querySelectorAll('.area-btn').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.area-btn').forEach(btn => btn.classList.remove('active'));
      button.classList.add('active');
      rerender();
    });
  });

  rerender();
}).catch(error => {
  const list = document.getElementById('list');
  list.innerHTML = `<div class="empty-state">Failed to load venue data: ${error.message}</div>`;
});
