1|# SAP SF Release Updates
2|
3|Live tracker for SAP SuccessFactors release updates. Pulls the latest changes from the SAP What's New Viewer and presents them in a clean, filterable dashboard - categorized by module with plain-English impact summaries.
4|
5|**Live at: https://sahirvhora.github.io/sf-release-update**
6|
7|## Features
8|
9|- **Multi-version support** - toggle between 1H 2026, 2H 2026 (preview), or all releases. The scraper auto-discovers available versions from SAP.
10|- **Release timeline** - preview and production dates for each release so teams know when changes hit their stack.
11|- **Weekly auto-refresh** - GitHub Actions scrapes the SAP What's New Viewer every Monday, discovers new versions automatically.
12|- **SF Compass-style accordion sidebar** - modules expand to show New/Changed/Deprecated/Deleted counts. Click a module header to filter the right panel; click a sub-item to narrow further.
13|- **Dark/Light theme toggle** - navy + gold dark theme (matches SF Compass), warm parchment light theme. Persisted to localStorage.
14|- **Impact classification** - Critical / High / Medium / Low derived from SAP's Action + Enablement + Reference Number columns.
15|- **Contextual plain-English summaries** - each update includes a unique "What this means for you" summary using the actual description text and timeline dates.
16|- **Full search & filter** - by module, impact level, action type, version, and free text search.
17|- **Release Readiness Checklist** - select your managed modules, generate a personalised checklist with Action Required / Review & Test / Informational categories, track progress with checkboxes (persisted in localStorage), export to JSON, and print.
18|- **Direct SAP links** - every update links to the official SAP Help Portal documentation.
19|- **Single-file HTML** - no dependencies, works offline with bundled data, deployed via GitHub Pages.
20|- **42 SF modules** tracked across Employee Central, Compensation, Recruiting, Platform, and more.
21|
22|## Architecture
23|
24|```
25|weekly cron -> scraper.py -> data/updates.json -> index.html -> GitHub Pages
26|```
27|
28|- `scraper.py` - Playwright-based scraper. Discovers available versions from SAP's filter, iterates through each, extracts all pages, classifies impact, generates plain-English summaries, and outputs structured JSON.
29|- `data/updates.json` - structured JSON (~600KB) with 492 items across 1H 2026 and 2H 2026 preview. Each item has impact classification, plain-English summary, release version tag, and absolute SAP links.
30|- `index.html` - single-file viewer with dark/light theme, version switcher, accordion sidebar, search, and filters. Reads `data/updates.json`.
31|
32|## Setup
33|
34|```bash
35|# Install dependencies
36|pip install -r requirements.txt
37|playwright install chromium
38|
39|# Run scraper (auto-discovers available versions)
40|python3 scraper.py
41|
42|# Serve locally
43|python3 -m http.server 8765
44|# Open http://localhost:8765
45|```
46|
47|## Automation
48|
49|The scraper runs automatically every **Monday at 06:00 UTC** via a GitHub Actions workflow (`.github/workflows/scrape.yml`). The workflow:
50|
51|1. Checks out the repo
52|2. Sets up Python 3.11 with Playwright
53|3. Runs `run_scraper.sh`, which executes `scraper.py` and commits/pushes any new data
54|
55|You can also trigger a scrape manually from the **Actions** tab → "Weekly SAP SF Release Scrape" → "Run workflow".
56|
57|The scraper auto-discovers available versions from SAP, so when 2H 2026 data is published (~September), it will be picked up automatically.
58|
59|## Deployment
60|
61|GitHub Pages from the repo root. The `data/updates.json` is committed alongside `index.html`.
62|
63|```bash
64|git add data/updates.json index.html scraper.py
65|git commit -m "Weekly SF update refresh"
66|git push
67|```
68|
69|## SAP Data Quirks
70|
71|- **Deprecation detection**: SAP marks deprecated items with `action="Changed"` and `refNumber="Deprecated"`. The impact classifier checks both fields.
72|- **Multi-line modules**: Some SAP items span multiple modules. The scraper takes the first (primary) module.
73|- **Preview items**: Future-release items appear in the current release view with "Preview" prefix. These are tagged as the upcoming release version.
74|- **Relative links**: SAP provides relative URLs; the scraper prepends `https://help.sap.com` and the viewer has a client-side fallback.
75|
76|## Related SAP SuccessFactors tools
77|
78|This project is part of a wider SAP SuccessFactors supplementary tools suite.
79|
80|Start with SF Compass for the full hub: https://sahirvhora.github.io/sf-compass/
81|
82|| Tool | Purpose |
83||---|---|
84|| SF Compass | Feasibility answers, implementation guidance, and links to the full tool suite |
85|| SF Release Update | Release impact tracking and testing focus |
86|| **SF Impact Brief** | **Personalised release briefs from this data - select modules, get a tiered action plan** |
87|| SF Pay Transparency | EU Pay Transparency readiness and evidence workflow framing |
88|| SF Value Navigator | Value realisation and sponsor-facing consulting framework |
89|| SF Position Integrity Checker | Position hierarchy, incumbency, and EC data-quality validation |
90|| SAPSF ObjectSync | Controlled foundation-object synchronisation between SF environments |
91|
92|