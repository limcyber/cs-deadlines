/**
 * Loads the merged venue dataset generated during the build step.
 *
 * Expected file location:
 *   ./assets/venues.json
 *
 * The returned value is an array of venue records.
 */
async function loadData() {
  const res = await fetch('./assets/venues.json');
  return await res.json();
}

/**
 * Collects all unique values for a given field across the full dataset.
 *
 * Why this exists:
 * - Some fields are single values (e.g. type)
 * - Some fields are arrays (e.g. domain)
 *
 * This helper normalizes both cases so the UI can build filter dropdown options.
 *
 * @param {Array<Object>} records - Full venue record list.
 * @param {string} key - Record field to inspect, such as "domain".
 * @returns {string[]} Sorted, unique, non-empty values.
 */
function uniqueValues(records, key) {
  const values = new Set();

  records.forEach(r => {
    const value = r[key];

    // If the field is an array (like domain), add each item separately.
    if (Array.isArray(value)) value.forEach(v => values.add(v));
    // Otherwise add the single scalar value if it exists.
    else if (value) values.add(value);
  });

  return Array.from(values).filter(Boolean).sort();
}

/**
 * Converts the deadlines array into displayable DOM content.
 *
 * Behavior:
 * - If there are no confirmed deadlines, return a plain fallback string.
 * - If deadlines exist, build a <ul> with one <li> per deadline item.
 *
 * Returning either a string or an element keeps the renderer flexible while
 * staying simple for this MVP.
 *
 * @param {Array<Object>} deadlines - Array like [{ kind, value }, ...]
 * @returns {string|HTMLUListElement}
 */
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

/**
 * Creates a readable venue/location string from optional fields.
 *
 * Example output:
 *   "Vancouver, Canada · 2026-12-01 → 2026-12-05"
 *
 * If nothing is known yet, return a friendly placeholder.
 *
 * @param {Object} r - Single venue record.
 * @returns {string}
 */
function formatVenue(r) {
  const parts = [];

  if (r.location) parts.push(r.location);

  if (r.venue_date_start || r.venue_date_end) {
    parts.push([r.venue_date_start, r.venue_date_end].filter(Boolean).join(' → '));
  }

  return parts.length ? parts.join(' · ') : 'Venue details not added yet';
}

/**
 * Renders the currently filtered venue list to the page.
 *
 * High-level flow:
 * 1. Clear the existing list
 * 2. Update the visible count
 * 3. Show an empty state if nothing matches
 * 4. Otherwise clone the HTML template once per record and fill it in
 *
 * @param {Array<Object>} records - Already-filtered records to display.
 */
function render(records) {
  const list = document.getElementById('list');
  const tpl = document.getElementById('cardTemplate');
  const resultCount = document.getElementById('resultCount');

  // Start fresh before rendering the new filtered results.
  list.innerHTML = '';
  resultCount.textContent = records.length;

  // Show a friendly message when no items match the current filter state.
  if (!records.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No venues match the current filters.';
    list.appendChild(empty);
    return;
  }

  records.forEach(r => {
    // Clone the HTML template for this specific venue record.
    const node = tpl.content.cloneNode(true);

    // Top badges: tier, type, and scan state.
    node.querySelector('.tier').textContent = r.tier;
    node.querySelector('.type').textContent = r.type;

    const scanState = node.querySelector('.scan-state');
    scanState.textContent = r.scan_enabled ? 'scan enabled' : 'catalog only';

    // Add a special visual style only when scanning is enabled.
    if (r.scan_enabled) scanState.classList.add('scan-on');

    // Main title section.
    node.querySelector('.title').textContent = `${r.short_name} — ${r.title}`;
    node.querySelector('.domains').textContent = `Domains: ${(r.domain || []).join(', ')}`;

    // Summary fields.
    node.querySelector('.year').textContent = `${r.year}`;
    node.querySelector('.status').textContent = r.status || 'catalog_seed';
    node.querySelector('.confidence').textContent = `${(r.confidence ?? 0).toFixed(2)}`;
    node.querySelector('.location').textContent = formatVenue(r);
    node.querySelector('.notes').textContent = r.notes || 'No notes yet.';

    // Deadlines may be rendered as plain text or as a <ul> element.
    const deadlinesHost = node.querySelector('.deadlines');
    const deadlineContent = formatDeadlines(r.deadlines);
    if (typeof deadlineContent === 'string') deadlinesHost.textContent = deadlineContent;
    else deadlinesHost.appendChild(deadlineContent);

    // Display up to three preview lines from the most recent scan output.
    const preview = node.querySelector('.preview');
    const previewLines = (r.scan_preview || []).slice(0, 3);

    if (previewLines.length) {
      previewLines.forEach(line => {
        const p = document.createElement('p');
        p.textContent = line;
        preview.appendChild(p);
      });
    } else {
      // Reuse the notes styling for the empty preview message in this MVP.
      preview.textContent = 'No scan preview available.';
      preview.classList.add('notes');
    }

    // Insert external links. innerHTML is used here because the markup is tiny
    // and predictable, but it assumes website/cfp_url values are trusted data.
    node.querySelector('.links').innerHTML =
      `<a href="${r.website}" target="_blank" rel="noopener">venue link</a> · ` +
      `<a href="${r.cfp_url}" target="_blank" rel="noopener">catalog / CFP link</a>`;

    list.appendChild(node);
  });
}

/**
 * Applies all active UI filters to the full dataset.
 *
 * Current filters:
 * - search query
 * - domain
 * - venue type
 * - tier
 * - scan state
 *
 * @param {Array<Object>} records - Full unfiltered dataset.
 * @returns {Array<Object>} Filtered subset.
 */
function applyFilters(records) {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const domain = document.getElementById('domainFilter').value;
  const type = document.getElementById('typeFilter').value;
  const tier = document.getElementById('tierFilter').value;
  const scan = document.getElementById('scanFilter').value;

  return records.filter(r => {
    // Build one searchable lowercase string from multiple fields.
    const hay = [r.title, r.short_name, ...(r.aliases || []), ...(r.domain || [])]
      .join(' ')
      .toLowerCase();

    if (q && !hay.includes(q)) return false;
    if (domain && !(r.domain || []).includes(domain)) return false;
    if (type && r.type !== type) return false;
    if (tier && r.tier !== tier) return false;
    if (scan === 'enabled' && !r.scan_enabled) return false;
    if (scan === 'catalog' && r.scan_enabled) return false;

    return true;
  });
}

/**
 * Bootstraps the page after the JSON data loads.
 *
 * Steps:
 * 1. Load dataset
 * 2. Build dynamic domain filter options
 * 3. Register filter event listeners
 * 4. Render the initial full list
 */
loadData().then(records => {
  const domainFilter = document.getElementById('domainFilter');

  // Fill the domain dropdown using the actual data values present in the file.
  uniqueValues(records, 'domain').forEach(v => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    domainFilter.appendChild(opt);
  });

  // Re-render whenever any control changes.
  const rerender = () => render(applyFilters(records));

  ['search', 'domainFilter', 'typeFilter', 'tierFilter', 'scanFilter'].forEach(id => {
    document.getElementById(id).addEventListener('input', rerender);
    document.getElementById(id).addEventListener('change', rerender);
  });

  // First paint using the complete dataset.
  rerender();
});
