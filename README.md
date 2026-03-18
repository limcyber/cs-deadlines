# CS Deadlines Hub MVP

A GitHub Pages + GitHub Actions starter project for a broad CS conference and workshop deadline tracker.

## What changed in this version
- All visible project text is now in English.
- The venue catalog has been expanded to 200 entries.
- The site now uses a wide one-row-per-venue layout instead of a three-cards-per-row grid.

## Project structure
- `data/venues.yml`: master venue catalog
- `data/instances.yml`: yearly scan results and confirmed instances
- `scripts/fetch.py`: scans only venues with `scan_enabled: true`
- `scripts/build_site.py`: merges venue metadata with the latest yearly instance and builds static JSON
- `docs/`: static site served by GitHub Pages
- `.github/workflows/update.yml`: scheduled scan + build + deploy workflow

## Operating model
1. Use `venues.yml` as the trusted catalog backbone.
2. Enable scanning only for venues with verified URLs.
3. Add newly discovered venues to the catalog after review.
4. Store yearly scan output and confirmed details in `instances.yml`.

## Quick start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/validate.py
python scripts/fetch.py
python scripts/build_site.py
```

## Notes
- The first set of starter venues is scan-enabled.
- Many of the newly added catalog entries are intentionally marked `scan_enabled: false` until their canonical URLs are reviewed.
- `instances.yml` can contain partial scan previews before deadlines are manually normalized.
