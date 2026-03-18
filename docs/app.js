async function loadData() {
  const res = await fetch('./assets/venues.json');
  return await res.json();
}

const THEME_KEY = 'cs-deadlines-theme';
const AREA_KEY = 'cs-deadlines-area';

const AREA_ORDER = ['AI+Data', 'Systems', 'Security', 'SE+Theory'];

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

const TIER_RANK = {
  top: 0,
  strong: 1,
  mid: 2,
  workshop: 3,
  fast: 4
};

function normalizeType(type) {
  return type === 'workshop' ? 'workshop' : 'conference';
}

function getBroadAreas(record) {
  const rawDomains = Array.isArray(record.domain) ? record.domain : [];
  const mapped = rawDomains.map((domain) => DOMAIN_TO_AREA[domain] || 'Systems');
  return Array.from(new Set(mapped));
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeText(value) {
  return String(value ?? '')
    .toLowerCase()
    .replace(/[^a-z0-9+]+/g, ' ')
    .trim();
}

function parseDeadlineValue(rawValue) {
  if (!rawValue) return null;
  if (rawValue instanceof Date) return Number.isNaN(rawValue.getTime()) ? null : rawValue;

  const original = String(rawValue).trim();
  const tzMatch = original.match(/\b(AOE|UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT)\b/i);
  const timezoneLabel = tzMatch ? tzMatch[1].toUpperCase() : null;

  let cleaned = original
    .replace(/\b(AOE|UTC|GMT|EST|EDT|CST|CDT|MST|MDT|PST|PDT)\b/ig, '')
    .replace(/\s+/g, ' ')
    .trim();

  if (/^\d{4}-\d{2}-\d{2}$/.test(cleaned)) {
    cleaned += 'T23:59:00';
  }

  const date = new Date(cleaned);
  if (Number.isNaN(date.getTime())) return null;

  return { date, timezoneLabel };
}

function getDeadlineTimezoneLabel(record, parsedItem) {
  return parsedItem?.timezoneLabel || record.default_timezone || record.timezone || 'Venue time';
}

function enrichDeadlines(record) {
  const rawDeadlines = Array.isArray(record.deadlines) ? record.deadlines : [];

  return rawDeadlines
    .map((deadline, index) => {
      const parsed = parseDeadlineValue(deadline?.value);
      if (!parsed) {
        return {
          ...deadline,
          parsedDate: null,
          timezoneLabel: deadline?.timezone || record.default_timezone || record.timezone || 'Venue time',
          order: index
        };
      }

      return {
        ...deadline,
        parsedDate: parsed.date,
        timezoneLabel: getDeadlineTimezoneLabel(record, parsed),
        order: index
      };
    })
    .sort((a, b) => {
      if (!a.parsedDate && !b.parsedDate) return a.order - b.order;
      if (!a.parsedDate) return 1;
      if (!b.parsedDate) return -1;
      return a.parsedDate - b.parsedDate;
    });
}

function getNow() {
  return new Date();
}

function getNextActionableDeadline(record) {
  const now = getNow();
  const parsedDeadlines = record.parsedDeadlines || [];
  const future = parsedDeadlines.find((deadline) => deadline.parsedDate && deadline.parsedDate > now);
  if (future) return future;
  return parsedDeadlines[parsedDeadlines.length - 1] || null;
}

function getStatusMeta(record) {
  const now = getNow();
  const deadlines = record.parsedDeadlines || [];
  const futureDeadlines = deadlines.filter((deadline) => deadline.parsedDate && deadline.parsedDate > now);

  if (!deadlines.length) {
    return { label: 'Not announced', className: 'status-unknown' };
  }

  if (!futureDeadlines.length) {
    return { label: 'Passed', className: 'status-passed' };
  }

  const next = futureDeadlines[0];
  const diffMs = next.parsedDate - now;
  const diffDays = diffMs / (1000 * 60 * 60 * 24);

  if (diffDays < 3) {
    return { label: 'Urgent', className: 'status-urgent' };
  }

  if (diffDays < 7) {
    return { label: 'Soon', className: 'status-soon' };
  }

  return { label: 'Upcoming', className: 'status-upcoming' };
}

function formatCountdown(targetDate) {
  if (!(targetDate instanceof Date) || Number.isNaN(targetDate.getTime())) {
    return 'Countdown unavailable';
  }

  const diffMs = targetDate - getNow();
  if (diffMs <= 0) {
    return 'Deadline passed';
  }

  const totalMinutes = Math.floor(diffMs / (1000 * 60));
  const days = Math.floor(totalMinutes / (60 * 24));
  const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
  const minutes = totalMinutes % 60;

  return `${days}d ${hours}h ${minutes}m left`;
}

function formatDateTime(date, options = {}) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return 'Not available';
  }

  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...options
  }).format(date);
}

function formatVenueDateRange(record) {
  const parts = [];
  if (record.location) parts.push(record.location);
  const dateRange = [record.venue_date_start, record.venue_date_end].filter(Boolean).join(' → ');
  if (dateRange) parts.push(dateRange);
  return parts.length ? parts.join(' · ') : 'Venue details not added yet';
}

function formatSourceLabel(record) {
  if (record.source_url) {
    try {
      const url = new URL(record.source_url);
      return `Source: ${url.hostname}`;
    } catch {
      return 'Source: linked';
    }
  }

  if (record.parser === 'manual_review') return 'Source: manual review needed';
  if (record.scan_enabled) return 'Source: automated scan';
  return 'Source: catalog seed';
}

function formatConfidence(record) {
  if (typeof record.confidence !== 'number' || record.confidence <= 0) {
    return 'Confidence: pending';
  }
  const label = record.confidence >= 0.85 ? 'high' : record.confidence >= 0.6 ? 'medium' : 'low';
  return `Confidence: ${record.confidence.toFixed(2)} (${label})`;
}

function getExtendedFrom(deadline) {
  return deadline?.extended_from || deadline?.original_value || deadline?.previous_value || null;
}

function formatDeadlineLine(record, deadline) {
  const kind = deadline.kind || 'deadline';
  const dateLabel = deadline.parsedDate ? formatDateTime(deadline.parsedDate) : (deadline.value || 'TBA');
  const timezoneLabel = deadline.timezoneLabel || record.default_timezone || record.timezone || 'Venue time';
  const extendedFrom = getExtendedFrom(deadline);

  let line = `<div class="timeline-kind">${escapeHtml(kind)}</div><div class="timeline-date">${escapeHtml(dateLabel)} <span class="tz-inline">(${escapeHtml(timezoneLabel)})</span></div>`;

  if (extendedFrom) {
    line += `<div class="timeline-extension">Extended from ${escapeHtml(extendedFrom)}</div>`;
  }

  return line;
}

function formatDeadlines(record) {
  const deadlines = record.parsedDeadlines || [];
  if (!deadlines.length) {
    return '<div class="timeline-empty">No confirmed deadlines yet.</div>';
  }

  return deadlines
    .map((deadline) => `<div class="timeline-row">${formatDeadlineLine(record, deadline)}</div>`)
    .join('');
}

function buildGoogleCalendarUrl(record, deadline) {
  if (!deadline?.parsedDate) return null;

  const end = deadline.parsedDate;
  const start = new Date(end.getTime() - 30 * 60 * 1000);
  const fmt = (date) => date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const text = encodeURIComponent(`${record.short_name} ${deadline.kind || 'deadline'}`);
  const details = encodeURIComponent(`Submission deadline for ${record.title}.`);
  const location = encodeURIComponent(record.location || 'Online / TBD');

  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${text}&dates=${fmt(start)}/${fmt(end)}&details=${details}&location=${location}`;
}

function buildICSData(record, deadline) {
  if (!deadline?.parsedDate) return null;

  const end = deadline.parsedDate;
  const start = new Date(end.getTime() - 30 * 60 * 1000);
  const fmt = (date) => date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const uid = `${record.id}-${deadline.kind || 'deadline'}@csdeadlineshub`;
  const safeTitle = `${record.short_name} ${deadline.kind || 'deadline'}`;
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//CS Deadlines Hub//EN',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${fmt(new Date())}`,
    `DTSTART:${fmt(start)}`,
    `DTEND:${fmt(end)}`,
    `SUMMARY:${safeTitle}`,
    `DESCRIPTION:Submission deadline for ${record.title}.`,
    `LOCATION:${record.location || 'Online / TBD'}`,
    'END:VEVENT',
    'END:VCALENDAR'
  ].join('\r\n');

  return URL.createObjectURL(new Blob([lines], { type: 'text/calendar' }));
}

function getSearchHaystack(record) {
  return normalizeText([
    record.title,
    record.short_name,
    ...(record.aliases || []),
    ...(record.domain || []),
    ...(record.broadAreas || []),
    record.location,
    record.type,
    record.tier
  ].join(' '));
}

function fuzzyMatch(record, query) {
  if (!query) return true;
  const haystack = getSearchHaystack(record);
  const tokens = normalizeText(query).split(/\s+/).filter(Boolean);
  if (!tokens.length) return true;

  return tokens.every((token) => {
    if (haystack.includes(token)) return true;
    const initials = normalizeText(record.short_name).replace(/\s+/g, '');
    return initials.includes(token);
  });
}

function sortRecords(records, mode) {
  const copy = [...records];

  if (mode === 'alphabetical') {
    copy.sort((a, b) => a.short_name.localeCompare(b.short_name));
    return copy;
  }

  if (mode === 'tier') {
    copy.sort((a, b) => {
      const tierDiff = (TIER_RANK[a.tier] ?? 99) - (TIER_RANK[b.tier] ?? 99);
      if (tierDiff !== 0) return tierDiff;
      return a.short_name.localeCompare(b.short_name);
    });
    return copy;
  }

  copy.sort((a, b) => {
    const aDeadline = getNextActionableDeadline(a)?.parsedDate;
    const bDeadline = getNextActionableDeadline(b)?.parsedDate;

    if (!aDeadline && !bDeadline) return a.short_name.localeCompare(b.short_name);
    if (!aDeadline) return 1;
    if (!bDeadline) return -1;

    return mode === 'latest' ? bDeadline - aDeadline : aDeadline - bDeadline;
  });

  return copy;
}

function enrichRecords(records) {
  return records.map((record) => ({
    ...record,
    broadAreas: getBroadAreas(record),
    displayType: normalizeType(record.type),
    parsedDeadlines: enrichDeadlines(record)
  }));
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

  records.forEach((record) => {
    const node = template.content.cloneNode(true);
    const statusMeta = getStatusMeta(record);
    const nextDeadline = getNextActionableDeadline(record);

    node.querySelector('.tier').textContent = record.tier;
    node.querySelector('.type').textContent = record.displayType;

    const scanState = node.querySelector('.scan-state');
    scanState.textContent = record.scan_enabled ? 'scan enabled' : 'catalog only';
    if (record.scan_enabled) scanState.classList.add('scan-on');

    const statusBadge = node.querySelector('.status-badge');
    statusBadge.textContent = statusMeta.label;
    statusBadge.classList.add(statusMeta.className);

    node.querySelector('.title').textContent = `${record.short_name} — ${record.title}`;
    node.querySelector('.domains').textContent = `Areas: ${record.broadAreas.join(', ')}`;
    node.querySelector('.year').textContent = `${record.year}`;

    node.querySelector('.location').textContent = record.location || 'Location not added yet';
    node.querySelector('.venue-dates').textContent = [record.venue_date_start, record.venue_date_end].filter(Boolean).join(' → ') || 'Venue dates not added yet';

    node.querySelector('.source').textContent = formatSourceLabel(record);
    node.querySelector('.confidence').textContent = formatConfidence(record);
    node.querySelector('.checked-at').textContent = record.checked_at ? `Last checked: ${formatDateTime(new Date(record.checked_at))}` : 'Last checked: not available';

    const nextDeadlineKind = node.querySelector('.next-deadline-kind');
    const countdown = node.querySelector('.countdown');
    const deadlineTime = node.querySelector('.deadline-time');
    const localTime = node.querySelector('.local-time');
    const calendarLinks = node.querySelector('.calendar-links');

    if (nextDeadline?.parsedDate) {
      const timezoneLabel = nextDeadline.timezoneLabel || 'Venue time';
      nextDeadlineKind.textContent = `Next: ${nextDeadline.kind || 'deadline'}`;
      countdown.textContent = formatCountdown(nextDeadline.parsedDate);
      deadlineTime.textContent = `Venue time: ${formatDateTime(nextDeadline.parsedDate)} (${timezoneLabel})`;
      localTime.textContent = `Your time: ${formatDateTime(nextDeadline.parsedDate, { timeZoneName: 'short' })}`;

      const googleUrl = buildGoogleCalendarUrl(record, nextDeadline);
      const icsUrl = buildICSData(record, nextDeadline);
      if (googleUrl) {
        calendarLinks.innerHTML = `<a href="${googleUrl}" target="_blank" rel="noopener">Google Calendar</a>`;
      }
      if (icsUrl) {
        const separator = googleUrl ? ' · ' : '';
        calendarLinks.innerHTML += `${separator}<a href="${icsUrl}" download="${record.id}-${nextDeadline.kind || 'deadline'}.ics">ICS</a>`;
      }
    } else {
      nextDeadlineKind.textContent = 'Next: not announced';
      countdown.textContent = 'Countdown unavailable';
      deadlineTime.textContent = 'Venue time: not announced';
      localTime.textContent = 'Your time: unavailable until a confirmed deadline exists';
      calendarLinks.textContent = 'Calendar links appear after a confirmed deadline is added.';
    }

    node.querySelector('.deadlines').innerHTML = formatDeadlines(record);
    node.querySelector('.notes').textContent = record.notes || 'No notes yet.';

    const preview = node.querySelector('.preview');
    const previewLines = (record.scan_preview || []).slice(0, 3);
    if (previewLines.length) {
      preview.innerHTML = previewLines.map((line) => `<p>${escapeHtml(line)}</p>`).join('');
    } else {
      preview.textContent = 'No scan preview available.';
      preview.classList.add('notes');
    }

    const links = [];
    if (record.website) {
      links.push(`<a href="${escapeHtml(record.website)}" target="_blank" rel="noopener">Venue link</a>`);
    }
    if (record.cfp_url) {
      links.push(`<a href="${escapeHtml(record.cfp_url)}" target="_blank" rel="noopener">Catalog / CFP link</a>`);
    }
    if (record.source_url) {
      links.push(`<a href="${escapeHtml(record.source_url)}" target="_blank" rel="noopener">Source link</a>`);
    }
    node.querySelector('.links').innerHTML = links.join(' · ');

    list.appendChild(node);
  });
}

function applyFilters(records) {
  const query = document.getElementById('search').value.trim();
  const type = document.getElementById('typeFilter').value;
  const scan = document.getElementById('scanFilter').value;
  const sort = document.getElementById('sortFilter').value;
  const topTierOnly = document.getElementById('topTierOnly').checked;
  const activeArea = document.querySelector('.chip.is-active')?.dataset.area || '';

  const filtered = records.filter((record) => {
    if (!fuzzyMatch(record, query)) return false;
    if (activeArea && !(record.broadAreas || []).includes(activeArea)) return false;
    if (type && record.displayType !== type) return false;
    if (scan === 'enabled' && !record.scan_enabled) return false;
    if (scan === 'catalog' && record.scan_enabled) return false;
    if (topTierOnly && record.tier !== 'top') return false;
    return true;
  });

  return sortRecords(filtered, sort);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const button = document.getElementById('themeToggle');
  if (!button) return;
  button.textContent = theme === 'dark' ? '🌙 Dark' : '☀️ Light';
}

function setupThemeToggle() {
  const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
  applyTheme(savedTheme);

  document.getElementById('themeToggle').addEventListener('click', () => {
    const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  });
}

function setupAreaButtons() {
  const savedArea = localStorage.getItem(AREA_KEY) || '';
  document.querySelectorAll('#areaButtons .chip').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.area === savedArea);
    button.addEventListener('click', () => {
      document.querySelectorAll('#areaButtons .chip').forEach((chip) => chip.classList.remove('is-active'));
      button.classList.add('is-active');
      localStorage.setItem(AREA_KEY, button.dataset.area || '');
      window.__rerender?.();
    });
  });

  if (!document.querySelector('#areaButtons .chip.is-active')) {
    document.querySelector('#areaButtons .chip[data-area=""]').classList.add('is-active');
  }
}

function boot(records) {
  const rerender = () => render(applyFilters(records));
  window.__rerender = rerender;

  ['search', 'typeFilter', 'scanFilter', 'sortFilter', 'topTierOnly'].forEach((id) => {
    const element = document.getElementById(id);
    element.addEventListener('input', rerender);
    element.addEventListener('change', rerender);
  });

  setupThemeToggle();
  setupAreaButtons();
  rerender();
  setInterval(rerender, 30000);
}

loadData().then((rawRecords) => {
  const records = enrichRecords(rawRecords);
  boot(records);
});
