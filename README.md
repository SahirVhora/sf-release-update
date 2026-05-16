# SF Update Pulse

Live tracker for SAP SuccessFactors release updates. Pulls the latest changes from the SAP What's New Viewer and presents them in a clean, filterable dashboard — categorized by module with plain-English impact summaries.

**Live at: https://sahirvhora.github.io/sf-update-pulse**

## Features

- **Weekly auto-refresh** — cron job scrapes the SAP What's New Viewer every Sunday
- **Module accordion navigation** — grouped by SF module (Employee Central, Compensation, Recruiting, etc.)
- **Impact classification** — Critical / High / Medium / Low derived from SAP's Action + Enablement columns
- **Plain-English summaries** — "What this means for you" for every update, in non-technical language
- **Full search & filter** — by module, impact level, action type (New/Changed/Deprecated/Deleted), and free text
- **Dark premium UI** — single-file HTML, no dependencies, works offline with bundled data
- **Direct SAP links** — every update links back to the official SAP documentation

## Architecture

```
weekly cron → scraper.py → data/updates.json → index.html → GitHub Pages
```

- `scraper.py` — Playwright-based scraper, extracts all pages from the SAP What's New Viewer
- `data/updates.json` — structured JSON with impact classification and plain-English summaries
- `index.html` — single-file dark-themed viewer, reads `data/updates.json`

## Setup

```bash
# Install Playwright
pip install playwright
playwright install chromium

# Run scraper
python3 scraper.py

# Serve locally
python3 -m http.server 8765
# Open http://localhost:8765
```

## Cron Job

Runs weekly via Hermes cron:

```
hermes cron create \
  --name "SF Update Pulse" \
  --schedule "0 9 * * 0" \
  --prompt "Run scraper.py in ~/projects/sapsf/sf-update-pulse, commit and push data/updates.json"
```

## Deployment

GitHub Pages from the repo root. The `data/updates.json` is committed alongside `index.html`.

```bash
git add data/updates.json index.html
git commit -m "Weekly SF update refresh"
git push
```
