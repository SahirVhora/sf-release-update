# SAP SF Release Updates

Live tracker for SAP SuccessFactors release updates. Pulls the latest changes from the SAP What's New Viewer and presents them in a clean, filterable dashboard - categorized by module with plain-English impact summaries.

**Live at: https://sahirvhora.github.io/sf-release-update**

## Features

- **Multi-version support** - toggle between 1H 2026, 2H 2026 (preview), or all releases. The scraper auto-discovers available versions from SAP.
- **Release timeline** - preview and production dates for each release so teams know when changes hit their stack.
- **Weekly auto-refresh** - cron job scrapes the SAP What's New Viewer every Sunday, discovers new versions automatically.
- **SF Compass-style accordion sidebar** - modules expand to show New/Changed/Deprecated/Deleted counts. Click a module header to filter the right panel; click a sub-item to narrow further.
- **Dark/Light theme toggle** - navy + gold dark theme (matches SF Compass), warm parchment light theme. Persisted to localStorage.
- **Impact classification** - Critical / High / Medium / Low derived from SAP's Action + Enablement + Reference Number columns.
- **Contextual plain-English summaries** - each update includes a unique "What this means for you" summary using the actual description text and timeline dates.
- **Full search & filter** - by module, impact level, action type, version, and free text search.
- **Direct SAP links** - every update links to the official SAP Help Portal documentation.
- **Single-file HTML** - no dependencies, works offline with bundled data, deployed via GitHub Pages.
- **42 SF modules** tracked across Employee Central, Compensation, Recruiting, Platform, and more.

## Architecture

```
weekly cron -> scraper.py -> data/updates.json -> index.html -> GitHub Pages
```

- `scraper.py` - Playwright-based scraper. Discovers available versions from SAP's filter, iterates through each, extracts all pages, classifies impact, generates plain-English summaries, and outputs structured JSON.
- `data/updates.json` - structured JSON (~600KB) with 492 items across 1H 2026 and 2H 2026 preview. Each item has impact classification, plain-English summary, release version tag, and absolute SAP links.
- `index.html` - single-file viewer with dark/light theme, version switcher, accordion sidebar, search, and filters. Reads `data/updates.json`.

## Setup

```bash
# Install Playwright
pip install playwright
playwright install chromium

# Run scraper (auto-discovers available versions)
python3 scraper.py

# Serve locally
python3 -m http.server 8765
# Open http://localhost:8765
```

## Cron Job

Runs weekly via Hermes cron (job ID: `3869df8f4724`):

```
hermes cron create \
  --name "SAP SF Release Updates" \
  --schedule "0 9 * * 0" \
  --prompt "Run scraper.py in ~/projects/sapsf/sf-release-update, commit and push data/updates.json"
```

The scraper auto-discovers available versions from SAP, so when 2H 2026 data is published (~September), it will be picked up automatically.

## Deployment

GitHub Pages from the repo root. The `data/updates.json` is committed alongside `index.html`.

```bash
git add data/updates.json index.html scraper.py
git commit -m "Weekly SF update refresh"
git push
```

## SAP Data Quirks

- **Deprecation detection**: SAP marks deprecated items with `action="Changed"` and `refNumber="Deprecated"`. The impact classifier checks both fields.
- **Multi-line modules**: Some SAP items span multiple modules. The scraper takes the first (primary) module.
- **Preview items**: Future-release items appear in the current release view with "Preview" prefix. These are tagged as the upcoming release version.
- **Relative links**: SAP provides relative URLs; the scraper prepends `https://help.sap.com` and the viewer has a client-side fallback.
