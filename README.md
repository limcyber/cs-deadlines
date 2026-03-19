# Computer Science Conferences Tracker

A lightweight GitHub Pages project for tracking Computer Science conference deadlines with a mix of automated scanning, conservative validation, and human review.

The repository has two goals:

- publish a clean public deadline view from static JSON assets
- keep an operational admin workflow for reviewing scanner output and curating records in `data/instances.yml`

## What This Project Does

- Maintains a venue catalog in `data/venues.yml`
- Stores year-specific conference instances in `data/instances.yml`
- Scans conference and CFP pages for date candidates
- Scores parsed candidates with a multi-phase auto-review pipeline
- Builds two static datasets:
  - `docs/assets/venues.json` for the public page
  - `docs/assets/admin.json` for the admin page
- Supports local review patch export/import from the admin UI

## Repository Layout

```text
data/
  venues.yml              Master venue catalog
  instances.yml           Year-specific instances and public deadline data
  review_patch.json       Default review patch file
  candidate_venues.json   Discovered venue candidates for manual triage

docs/
  index.html              Public page
  admin.html              Admin page
  app.js                  Public page logic
  admin.js                Admin page logic
  style.css               Shared public styles
  admin.css               Admin-specific styles
  assets/
    venues.json           Built public dataset
    admin.json            Built admin dataset

scripts/
  fetch.py                        Fetch and parse conference pages
  auto_review.py                  Score parsed candidates
  build_site.py                   Build static JSON assets
  validate.py                     Validate YAML structure and values
  apply_review_patch.py           Apply exported review patch JSON
  apply_review_bundle.py          Apply patch + validate + build in one command
  batch_confirm_from_parsed.py    Generate review patches from parsed candidates
  seed_confirmed_history.py       Create conservative bootstrap history rows
  discover_candidates.py          Discover possible new venues from external sources
  deadline_utils.py               Shared parsing/scoring helpers

.github/workflows/
  update.yml                      Main fetch/review/build/deploy workflow
  discover-candidates.yml         Candidate discovery workflow
```

## Data Model

### `venues.yml`

`data/venues.yml` is the venue catalog. Each venue entry describes the recurring conference identity and scan configuration.

Common fields:

- `id`
- `title`
- `short_name`
- `aliases`
- `domain`
- `type`
- `tier`
- `recurring`
- `active`
- `website`
- `cfp_url`
- `default_timezone`
- `parser`
- `scan_enabled`
- `notes`

### `instances.yml`

`data/instances.yml` stores year-specific records. These are the rows that eventually become public deadline entries.

Common fields:

- `id`
- `venue_id`
- `year`
- `status`
- `deadlines`
- `parsed_deadlines`
- `venue_date_start`
- `venue_date_end`
- `location`
- `source_url`
- `checked_at`
- `confidence`
- `scan_preview`
- `notes`
- `auto_review`

### Statuses

The validator currently accepts these statuses:

- `catalog_seed`
- `placeholder`
- `awaiting_cfp`
- `scanned`
- `scan_failed`
- `review_required`
- `confirmed`
- `auto_confirmed`
- `rejected`
- `closed`
- `conflict`

Practical meaning:

- `confirmed`: manually reviewed and intended for public display
- `auto_confirmed`: promoted automatically by the scoring pipeline
- `review_required`: scanner found plausible data but a human should verify it
- `scanned`: raw scanner output that has not been promoted
- `scan_failed`: source access or parsing failure
- `catalog_seed`: catalog-only record with no public-ready deadline yet


### Public page

The public page is `docs/index.html`.

It reads `docs/assets/venues.json` and shows one current record per venue. `scripts/build_site.py` merges venues and instances, then exposes:

- confirmed and auto-confirmed records
- catalog/manual venues
- selected scanner previews that meet a minimum confidence floor

The public UI includes:

- search
- area filters
- type/tier/scan-state filters
- sorting
- black/white theme toggle
- deadline countdowns


## Local Setup

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Main packages:

- `PyYAML`
- `requests`
- `beautifulsoup4`
- `python-dateutil`
- `livereload`

## Local Development

Quick build:

```bash
python3 scripts/build_site.py
```

Run a static preview server:

```bash
cd docs
python3 -m http.server 8000
```

Optional dev helper:

```bash
python3 dev.py
```

## Validation

Run validation before building or committing data changes:

```bash
python3 scripts/validate.py
```

The validator checks:

- top-level YAML structure
- required fields
- duplicate IDs
- URL format
- ISO date/datetime format
- confidence values in `[0, 1]`
- deadline object structure
- parsed deadline structural sanity

## Build Process

Build the static JSON assets with:

```bash
python3 scripts/build_site.py
```

Outputs:

- `docs/assets/venues.json`
- `docs/assets/admin.json`

What `build_site.py` does:

- merges the latest instance for each venue
- normalizes display fields such as location
- keeps the public dataset more conservative than the admin dataset

## Main Update Pipeline

The primary local update flow is:

```bash
python3 manual_update.py --phase 3
```

That wrapper runs:

1. `scripts/validate.py`
2. `scripts/fetch.py`
3. `scripts/auto_review.py --phase 3`
4. `scripts/build_site.py`

Useful variants:

```bash
python3 manual_update.py --validate-only
python3 manual_update.py --build-only
python3 manual_update.py --skip-fetch
python3 manual_update.py --phase 1
python3 manual_update.py --phase 2
python3 manual_update.py --phase 3 --seed-history
python3 manual_update.py --phase 3 --discover-candidates
```

## Daily Operations Checklist

Use this when you want a practical maintenance routine instead of remembering each script by hand.

### 1. Refresh and rebuild

```bash
python3 manual_update.py --phase 3
```

What to check after it finishes:

- validation passes
- `data/instances.yml` changed in expected ways
- `docs/assets/venues.json` and `docs/assets/admin.json` were rebuilt

### 2. Review scanner output

Open the admin page and inspect:

- `review_required` records
- `scan_failed` records
- low-confidence or suspicious parsed deadlines
- venue cards showing `Location TBD` or missing structured deadlines

### 3. Apply manual fixes

Choose one of these:

- edit `data/instances.yml` directly for small manual corrections
- use the admin page to prepare a local review patch, then apply it

Patch-based flow:

```bash
python3 scripts/apply_review_bundle.py /path/to/review-patch.json
```

### 4. Sanity-check the public page

Before pushing:

- open `docs/index.html`
- confirm sorting still behaves correctly
- confirm deadline text is not unexpectedly falling back to `Deadline not announced`
- check a few Venue/CFP links
- check both black and white themes

### 5. Sanity-check the admin page

### 6. Candidate triage

When discovery is enabled or the candidate file changed:

```bash
python3 scripts/discover_candidates.py
```

Review:

- `data/candidate_venues.json`
- whether the candidate is already tracked under another acronym
- whether the source appears official enough to promote into `data/venues.yml`

## Fetching and Parsing

Use the scanner directly with:

```bash
python3 scripts/fetch.py
```

`fetch.py`:

- requests venue pages using a stable user-agent
- strips page boilerplate
- extracts candidate lines
- parses dates from visible text and script blobs
- attaches `parsed_deadlines`, `scan_preview`, `checked_at`, and related review metadata to instances

The scanner writes back to `data/instances.yml`.

## Auto Review Pipeline

After fetching, parsed candidates can be scored by `scripts/auto_review.py`.

Run manually:

```bash
python3 scripts/auto_review.py --phase 3
python3 scripts/auto_review.py --phase 1 --dry-run
```

### Phases

- Phase 1: strict and history-dependent
- Phase 2: moderate, allows limited historical drift
- Phase 3: more capable, adds parser-family and prediction-alignment signals

The auto-review step can:

- keep a record in review
- reject noisy candidates
- auto-confirm high-confidence candidates

It also writes `auto_review` metadata into instances so the admin page can explain why a record was or was not promoted.

## Review Workflow

### Apply a review patch

If you exported a patch from the admin page, apply it with:

```bash
python3 scripts/apply_review_patch.py /path/to/review-patch.json
python3 scripts/validate.py
python3 scripts/build_site.py
```

There is also a convenience wrapper:

```bash
python3 scripts/apply_review_bundle.py
python3 scripts/apply_review_bundle.py /path/to/review-patch.json
```

That wrapper runs:

1. `scripts/apply_review_patch.py`
2. `scripts/validate.py`
3. `scripts/build_site.py`

### Review patch format

`scripts/apply_review_patch.py` accepts either:

- a top-level object containing `records`
- a raw list of patch records

Patched fields are intentionally whitelisted:

- `venue_id`
- `year`
- `status`
- `deadlines`
- `venue_date_start`
- `venue_date_end`
- `location`
- `source_url`
- `checked_at`
- `confidence`
- `scan_preview`
- `notes`

## Batch Confirm Helper

To generate a review patch from parsed candidates:

```bash
python3 scripts/batch_confirm_from_parsed.py --dry-run
python3 scripts/batch_confirm_from_parsed.py --apply
```

This helper:

- filters instances by status
- picks the best parsed deadline
- emits a patch rather than directly mutating YAML
- optionally applies the patch using the same patch path as the admin workflow

## Bootstrap Confirmed History Seeds

Phase 1 is intentionally conservative, so some venues may need historical confirmed rows before auto-review becomes useful.

Generate bootstrap seeds with:

```bash
python3 scripts/seed_confirmed_history.py --limit 8
python3 scripts/seed_confirmed_history.py --dry-run
```

Or through the wrapper:

```bash
python3 manual_update.py --phase 1 --seed-history
```

This step:

- looks for strong structured parsed deadlines
- requires official or official CFP sources
- creates a previous-year confirmed row
- marks it with `seed_meta`

These seeds are operational helpers, not ideal archival truth, and should be replaced later with real historical records when available.

## Candidate Discovery

To discover new untracked venues from external feeds:

```bash
python3 scripts/discover_candidates.py
python3 scripts/discover_candidates.py --min-confidence 0.6 --limit 150
```

Discovery writes to:

- `data/candidate_venues.json`

Sources currently include:

- WikiCFP
- AI deadline aggregators
- selected IEEE and security conference listings

This file is for manual triage. Discovery does not automatically add venues to `data/venues.yml`.

## GitHub Actions

### Main deploy workflow

`.github/workflows/update.yml` runs on:

- push to `main`
- manual dispatch
- a 6-hour cron schedule

It performs:

1. dependency install
2. validation
3. fetch
4. auto review
5. build
6. GitHub Pages deploy

### Candidate discovery workflow

`.github/workflows/discover-candidates.yml` runs on:

- manual dispatch
- daily cron

It refreshes `data/candidate_venues.json` and commits the updated candidate file when it changes.

## Security and Access Notes

This project is intentionally static-first. That keeps deployment simple, but it also means:

- the admin page is not truly secure
- anything sent to the browser should be treated as inspectable by the user

Practical implication:

- do not rely on `docs/admin.html` for strong authentication or private data protection

## Operational Notes

- The public page includes automatically collected data and may be wrong; use official conference links to confirm deadlines.
- The admin page stores draft edits locally in browser storage until you export them.
- The build currently shows one latest instance per venue in the merged datasets.
- Validation is strict on purpose; if YAML fails validation, fix the data before rebuilding.

## Recommended Local Commands

Most useful commands during normal maintenance:

```bash
python3 scripts/validate.py
python3 scripts/build_site.py
python3 manual_update.py --phase 3
python3 scripts/apply_review_bundle.py
python3 scripts/discover_candidates.py
```

## Maintenance Tips

- Prefer official CFP pages over aggregator pages when promoting a deadline to `confirmed`.
- Treat WikiCFP and similar sources as lead-generation or cross-checking inputs, not final truth.
- If a 2026 deadline is missing but a credible 2025 pattern exists, document that fallback clearly in notes before exposing it publicly.
- When a venue is catalog-only, it is better to keep it conservative than to publish a guessed deadline.
- Rebuild the site after any YAML edit, even if the change feels small.

## License

MIT
