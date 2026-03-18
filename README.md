# CS Deadlines — Final Lightweight Version

A GitHub Pages + GitHub Actions conference deadline tracker focused on three things:
- efficient discovery by broad area and strong search
- reliable scheduled collection with controlled scanning
- safe publication of confirmed information only

## What this version implements

### Phase 2
- parser separation (`manual`, `generic_dates`, `structured_dates`)
- `scan_enabled` discipline for scheduled scans
- structured `scan_preview` storage
- standardized deadline schema
- next actionable deadline computation
- stronger search across title, short name, aliases, and tokens
- scheduled update workflow
- structured scan failure logging

### Phase 3
- source priority metadata
- `high / medium / low` confidence labels
- preview vs confirmed separation
- publication gating for public countdowns
- conflict visibility (`review_required`, `conflict_reason`)
- manual override support
- extension history support (`extended_from`, `previous_value`, `original_value`)
- public source transparency in the UI

## Project structure
- `data/venues.yml` — master venue catalog
- `data/instances.yml` — yearly scan state, previews, and confirmed deadlines
- `data/manual_overrides.yml` — maintainer corrections for specific venue/year records
- `data/scan_failures.json` — last run failure log
- `data/scan_run_summary.json` — last run machine-readable summary
- `scripts/fetch.py` — scheduled collection pipeline
- `scripts/build_site.py` — promotion and publication-safe static build
- `scripts/validate.py` — schema and consistency checks
- `docs/` — static frontend for GitHub Pages
- `.github/workflows/update.yml` — scheduled scan + build + deploy workflow

## Operating model
1. Treat `venues.yml` as the trusted catalog backbone.
2. Scan only explicitly approved venues (`scan_enabled: true`).
3. Store machine-detected candidates in `scan_preview`.
4. Publish only confirmed or policy-approved deadlines.
5. Use manual overrides for ambiguous or exceptional cases.

## Quick start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/validate.py
python scripts/build_site.py
```

## Full local pipeline
```bash
python scripts/validate.py
python scripts/fetch.py
python scripts/build_site.py
```

## Notes
- The repository includes sample confirmed instances so the UI works immediately.
- Most catalog venues still remain seed entries until their URLs and parser behavior are verified.
- The public UI intentionally prefers “Not announced” over low-confidence countdowns.
