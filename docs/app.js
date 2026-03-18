async function loadData() {
  const res = await fetch('./assets/venues.json');
  return await res.json();
}

function uniqueValues(records, key) {
  const values = new Set();
  records.forEach(r => (r[key] || []).forEach ? r[key].forEach(v => values.add(v)) : values.add(r[key]));
  return Array.from(values).filter(Boolean).sort();
}

function render(records) {
  const list = document.getElementById('list');
  const tpl = document.getElementById('cardTemplate');
  list.innerHTML = '';

  records.forEach(r => {
    const node = tpl.content.cloneNode(true);
    node.querySelector('.tier').textContent = r.tier;
    node.querySelector('.type').textContent = r.type;
    node.querySelector('.title').textContent = `${r.short_name} ${r.year}`;
    node.querySelector('.domains').textContent = `분야: ${(r.domain || []).join(', ')}`;
    node.querySelector('.year').textContent = `연도: ${r.year}`;
    node.querySelector('.status').textContent = `상태: ${r.status}`;
    node.querySelector('.confidence').textContent = `confidence: ${r.confidence ?? 0}`;
    const preview = node.querySelector('.preview');
    (r.scan_preview || []).slice(0, 3).forEach(line => {
      const p = document.createElement('p');
      p.textContent = line;
      preview.appendChild(p);
    });
    node.querySelector('.links').innerHTML = `<a href="${r.website}" target="_blank" rel="noopener">website</a> · <a href="${r.cfp_url}" target="_blank" rel="noopener">cfp</a>`;
    list.appendChild(node);
  });
}

function applyFilters(records) {
  const q = document.getElementById('search').value.trim().toLowerCase();
  const domain = document.getElementById('domainFilter').value;
  const type = document.getElementById('typeFilter').value;
  const tier = document.getElementById('tierFilter').value;

  return records.filter(r => {
    const hay = [r.title, r.short_name, ...(r.domain || [])].join(' ').toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (domain && !(r.domain || []).includes(domain)) return false;
    if (type && r.type !== type) return false;
    if (tier && r.tier !== tier) return false;
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
  ['search', 'domainFilter', 'typeFilter', 'tierFilter'].forEach(id => {
    document.getElementById(id).addEventListener('input', rerender);
    document.getElementById(id).addEventListener('change', rerender);
  });
  rerender();
});
