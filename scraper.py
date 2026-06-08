1|#!/usr/bin/env python3
2|"""
3|SAP SF Release Updates - Scraper
4|Fetches the latest SAP SuccessFactors What's New data and outputs structured JSON.
5|Run: python3 scraper.py
6|Output: data/updates.json
7|"""
8|
9|import html, json, os, re, sys, time
10|from datetime import datetime
11|from pathlib import Path
12|
13|# --- Config ---
14|BASE_URL = "https://help.sap.com/whats-new/8fcf4960eea24f78b1d7613da406a885"
15|OUTPUT_DIR = Path(__file__).parent / "data"
16|OUTPUT_FILE = OUTPUT_DIR / "updates.json"
17|INDEX_FILE = Path(__file__).parent / "index.html"
18|# How many pages to fetch (25 items per page). Set high, script stops when no more data.
19|MAX_PAGES = 50
20|
21|# --- Impact Classification ---
22|# Impact = f(Action, Enablement)
23|def classify_impact(action: str, enablement: str, ref_number: str = "") -> dict:
24|    """Return impact level and label based on SAP's Action + Enablement columns.
25|    SAP quirk: deprecated items often have action='Changed' with refNumber='Deprecated'."""
26|    action = (action or "").strip().lower()
27|    enablement = (enablement or "").strip().lower()
28|    ref_number = (ref_number or "").strip().lower()
29|    
30|    # Detect deprecation from either the action field or the reference number
31|    is_deprecated = action in ("deprecated", "deleted") or ref_number == "deprecated"
32|    
33|    if is_deprecated:
34|        if enablement in ("required", "automatically on", ""):
35|            return {"level": "critical", "label": "Critical", "color": "#ef4444"}
36|        return {"level": "high", "label": "High", "color": "#f97316"}
37|    
38|    # High: Major enablement changes or forced changes
39|    if enablement == "major":
40|        return {"level": "high", "label": "High", "color": "#f97316"}
41|    if action == "changed" and enablement in ("required", "automatically on"):
42|        return {"level": "high", "label": "High", "color": "#f97316"}
43|    
44|    # Medium: Changes needing config or new major features
45|    if action == "changed" and enablement in ("minor", "customer configured"):
46|        return {"level": "medium", "label": "Medium", "color": "#eab308"}
47|    if action == "new" and enablement == "major":
48|        return {"level": "medium", "label": "Medium", "color": "#eab308"}
49|    
50|    # Low: Everything else
51|    return {"level": "low", "label": "Low", "color": "#22c55e"}
52|
53|
54|def generate_plain_english(action: str, enablement: str, title: str, description: str) -> str:
55|    """Generate a contextual plain-English summary incorporating title and description details."""
56|    action = (action or "").strip().lower()
57|    enablement = (enablement or "").strip().lower()
58|    
59|    # Extract first sentence for context
60|    first_sentence = description.split(".")[0].strip() if description else ""
61|    # Shorten very long sentences
62|    if len(first_sentence) > 200:
63|        first_sentence = first_sentence[:197] + "..."
64|    
65|    # Extract dates if present
66|    import re
67|    dates = re.findall(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', description)
68|    date_str = ""
69|    if dates:
70|        # Find full date match (not just captured month group)
71|        full_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', description)
72|        if full_match:
73|            date_str = f" Timeline: {full_match.group(0)}."
74|    
75|    # Detect urgency words
76|    urgent_words = ["deleted", "removed", "no longer available", "end of", "must", "required"]
77|    is_urgent = any(w in description.lower() for w in urgent_words)
78|    
79|    if action == "deprecated" or (action == "changed" and "deprecated" in description.lower()):
80|        if is_urgent:
81|            return f"Will stop working - you need a replacement.{date_str} Check the linked SAP Note for migration steps."
82|        return f"Being phased out. Start planning your move to the replacement now.{date_str}"
83|    
84|    if action == "deleted":
85|        return f"Already removed. If you relied on this, switch to the alternative immediately.{date_str}"
86|    
87|    if action == "new":
88|        if enablement == "major":
89|            return f"Significant new capability - could change how you work. {first_sentence} Review config steps and test in sandbox first."
90|        if enablement in ("minor", "customer configured"):
91|            return f"Available when you're ready. {first_sentence} Test in non-production before enabling broadly."
92|        return f"Active automatically - no setup needed. {first_sentence}"
93|    
94|    if action == "changed":
95|        if is_urgent:
96|            return f"Important change you need to act on.{date_str} Review the details - this affects your system automatically."
97|        if enablement == "major":
98|            return f"Significant update. {first_sentence} Plan configuration changes and communicate to users."
99|        if enablement in ("minor", "customer configured"):
100|            return f"Minor update - configure if useful. {first_sentence}"
101|        return f"Updated automatically. {first_sentence}"
102|    
103|    # Fallback with context
104|    return f"Review this change. {first_sentence}"
105|
106|
107|# --- Scraping ---
108|def scrape_with_playwright():
109|    """Use Playwright to extract all rows from the What's New Viewer, across all available versions."""
110|    try:
111|        from playwright.sync_api import sync_playwright
112|    except ImportError:
113|        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
114|        sys.exit(1)
115|    
116|    all_items = []
117|    
118|    with sync_playwright() as p:
119|        browser = p.chromium.launch(headless=True, args=[
120|            '--disable-blink-features=AutomationControlled',
121|            '--no-sandbox',
122|            '--disable-dev-shm-usage'
123|        ])
124|        context = browser.new_context(
125|            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
126|            viewport={"width": 1920, "height": 1080},
127|            locale="en-US"
128|        )
129|        context.add_init_script("""
130|            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
131|            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
132|        """)
133|        page = context.new_page()
134|        
135|        print(f"Loading {BASE_URL} ...")
136|        try:
137|            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=120000)
138|        except Exception as e:
139|            print(f"Initial load warning: {e}. Trying load event...")
140|            page.goto(BASE_URL, wait_until="load", timeout=120000)
141|        
142|        # Dismiss cookie consent
143|        print("Checking for cookie consent banner...")
144|        try:
145|            consent_btn = page.wait_for_selector(
146|                'button:has-text("Accept All"), button:has-text("Accept Cookies"), '
147|                'button:has-text("OK"), button#truste-consent-button, '
148|                'a:has-text("Accept All"), .trustarc-agree-btn',
149|                timeout=15000
150|            )
151|            if consent_btn:
152|                print("Dismissing cookie consent banner...")
153|                consent_btn.click()
154|                page.wait_for_timeout(2000)
155|        except:
156|            print("No cookie consent banner found (or already accepted).")
157|        
158|        try:
159|            page.evaluate("""
160|                const banners = document.querySelectorAll('#truste-consent-track, .trustarc-banner, [id*="consent_blackbar"]');
161|                banners.forEach(b => b.style.display = 'none');
162|            """)
163|        except:
164|            pass
165|        
166|        print("Waiting for page to render...")
167|        try:
168|            page.wait_for_selector("table tbody tr, button:has-text('Product')", timeout=45000)
169|        except:
170|            print("WARNING: Selectors not found. Page might not have loaded fully.")
171|        
172|        page.wait_for_timeout(5000)
173|        
174|        # --- Discover available versions ---
175|        available_versions = []
176|        current_year = datetime.now().year
177|        
178|        # Strategy 1: Look for the version filter button's current display text
179|        try:
180|            ver_btn = page.query_selector('button:has-text("Software Version")')
181|            if ver_btn:
182|                btn_text = ver_btn.inner_text().strip()
183|                print(f"  Version button text: '{btn_text}'")
184|                ver_btn.click()
185|                page.wait_for_timeout(2500)
186|                
187|                # The SAP UI5 dialog with version checkboxes should now be open.
188|                # Strategy 2a: Look for SAP UI5 list items with version patterns
189|                raw_candidates = page.evaluate("""
190|                    () => {
191|                        const results = [];
192|                        // Target SAP UI5 dialog/popover specifically
193|                        const popups = document.querySelectorAll('.sapMDialog, .sapMPopover, [role="dialog"], .sapUiRespGrid');
194|                        const containers = popups.length > 0 ? popups : [document];
195|                        containers.forEach(container => {
196|                            // SAP UI5 checkboxes with labels
197|                            container.querySelectorAll('.sapMCb').forEach(cb => {
198|                                const label = cb.querySelector('.sapMCbLabel');
199|                                if (label) {
200|                                    const t = label.textContent.trim();
201|                                    if (/^[12]H\\s+20\\d\\d/.test(t)) results.push(t);
202|                                }
203|                            });
204|                            // Also check regular labels near checkboxes
205|                            container.querySelectorAll('label').forEach(lbl => {
206|                                const t = lbl.textContent.trim();
207|                                // Only match clean version strings: "1H 2026", "2H 2026", "2H 2026 (Preview)"
208|                                if (/^[12]H\\s+20\\d\\d(\\s*\\(Preview\\))?$/.test(t) && !results.includes(t)) {
209|                                    results.push(t);
210|                                }
211|                            });
212|                            // Check list items
213|                            container.querySelectorAll('li, [role="option"]').forEach(li => {
214|                                const t = li.textContent.trim();
215|                                if (/^[12]H\\s+20\\d\\d/.test(t) && t.length < 30 && !results.includes(t)) {
216|                                    results.push(t);
217|                                }
218|                            });
219|                        });
220|                        return results;
221|                    }
222|                """)
223|                print(f"  Raw version candidates: {raw_candidates}")
224|                
225|                # Filter: only keep versions from current year and next year
226|                for v in raw_candidates:
227|                    v = v.strip()
228|                    match = re.match(r'[12]H\s+(\d{4})', v)
229|                    if match:
230|                        year = int(match.group(1))
231|                        if year >= current_year and year <= current_year + 1:
232|                            available_versions.append(v)
233|                
234|                # Close dropdown by pressing Escape (more reliable than clicking body)
235|                page.keyboard.press("Escape")
236|                page.wait_for_timeout(1000)
237|        except Exception as e:
238|            print(f"  Version discovery error: {e}")
239|        
240|        # Strategy 3: Fallback - scrape default view + infer versions from current year
241|        if not available_versions:
242|            print("  No versions found via dropdown. Using current-year defaults.")
243|            available_versions = [f"1H {current_year}", f"2H {current_year} (Preview)"]
244|        
245|        # Deduplicate and sort (1H before 2H). Prefer "(Preview)" variants when duplicates exist.
246|        seen_ver = {}
247|        for v in available_versions:
248|            v = v.strip()
249|            key = re.sub(r'\s*\(Preview\)\s*', '', v).strip()
250|            # Keep the variant with "(Preview)" if both exist
251|            if key not in seen_ver or ('(Preview)' in v and '(Preview)' not in seen_ver[key]):
252|                seen_ver[key] = v
253|        deduped = list(seen_ver.values())
254|        available_versions = sorted(deduped, key=lambda x: (re.search(r'\d{4}', x).group() if re.search(r'\d{4}', x) else '0') + ('0' if '1H' in x else '1'))
255|        
256|        # Append "(Preview)" to 2H versions whose production date is still in the future
257|        final_versions = []
258|        for v in available_versions:
259|            match = re.match(r'2H\s+(\d{4})', v)
260|            if match:
261|                year = int(match.group(1))
262|                prod_date = datetime(year, 11, 15)
263|                if prod_date > datetime.now() and '(Preview)' not in v:
264|                    v = v + ' (Preview)'
265|            final_versions.append(v)
266|        available_versions = final_versions
267|        
268|        print(f"Selected versions: {available_versions}")
269|        
270|        # --- Scrape each version ---
271|        prev_first_title = None  # Track first item of previous version to detect failed switches
272|        for ver_idx, version_name in enumerate(available_versions):
273|            print(f"\n--- Scraping version: {version_name} ---")
274|            
275|            if ver_idx > 0:
276|                # Switch to this version
277|                try:
278|                    # Strip "(Preview)" for lookup since SAP's dropdown uses plain version names
279|                    lookup_name = re.sub(r'\s*\(Preview\)\s*', '', version_name).strip()
280|                    ver_btn = page.query_selector('button:has-text("Software Version")')
281|                    if ver_btn:
282|                        ver_btn.click()
283|                        page.wait_for_timeout(1500)
284|                        # Find and click the option - try exact text match first
285|                        option = page.query_selector(f'text="{lookup_name}"')
286|                        if not option:
287|                            option = page.query_selector(f'[title="{lookup_name}"]')
288|                        if not option:
289|                            # Try SAP UI5 checkbox label
290|                            labels = page.query_selector_all('.sapMCbLabel, label')
291|                            for lbl in labels:
292|                                if lbl.inner_text().strip() == lookup_name:
293|                                    option = lbl
294|                                    break
295|                        if option:
296|                            option.click()
297|                            page.wait_for_timeout(3000)  # Wait for data reload
298|                        else:
299|                            print(f"  Could not find option for {lookup_name}, skipping.")
300|                            # Close dropdown and continue
301|                            page.keyboard.press("Escape")
302|                            page.wait_for_timeout(500)
303|                            continue
304|                        # Close dropdown after selection
305|                        page.keyboard.press("Escape")
306|                        page.wait_for_timeout(500)
307|                except Exception as e:
308|                    print(f"  Failed to switch version: {e}")
309|                    continue
310|            
311|            # Extract all pages for this version
312|            page_num = 1
313|            version_items = 0
314|            while page_num <= MAX_PAGES:
315|                rows = page.query_selector_all("table tbody tr")
316|                if not rows:
317|                    print(f"  No rows on page {page_num}. Done with {version_name}.")
318|                    break
319|                
320|                # --- Guards against failed version switches ---
321|                # Guard 1: if the first page yields 0 valid rows, the version has no data
322|                valid_row_count = sum(1 for row in rows if len(row.query_selector_all("td")) >= 8)
323|                if page_num == 1 and valid_row_count == 0:
324|                    print(f"  ⚠ Version {version_name} returned 0 items - skipping (no data published yet).")
325|                    break
326|                
327|                # Guard 2: if first item matches previous version's first item, the switch likely failed
328|                if ver_idx > 0 and page_num == 1 and prev_first_title:
329|                    first_cell = rows[0].query_selector("td")
330|                    if first_cell:
331|                        current_first_title = (first_cell.inner_text() or "").strip().removeprefix("Preview ")
332|                        if current_first_title == prev_first_title:
333|                            print(f"  ⚠ Version switch to {version_name} appears to have failed - first item matches {prev_first_title[:60]}...")
334|                            print(f"  Skipping {version_name} (data unchanged from previous version).")
335|                            break
336|                # --- End guards ---
337|                
338|                for row in rows:
339|                    cells = row.query_selector_all("td")
340|                    if len(cells) < 8:
341|                        continue
342|                    
343|                    title = (cells[0].inner_text() or "").strip().removeprefix("Preview ")
344|                    description = (cells[1].inner_text() or "").strip().removesuffix("See More").strip()
345|                    product = (cells[2].inner_text() or "").strip()
346|                    module_raw = (cells[3].inner_text() or "").strip()
347|                    module = module_raw.split("\n")[0].strip()
348|                    feature = (cells[4].inner_text() or "").strip()
349|                    lifecycle = (cells[5].inner_text() or "").strip()
350|                    action = (cells[6].inner_text() or "").strip()
351|                    enablement = (cells[7].inner_text() or "").strip()
352|                    ref_number = (cells[8].inner_text() or "").strip() if len(cells) > 8 else ""
353|                    demo = (cells[9].inner_text() or "").strip() if len(cells) > 9 else ""
354|                    version_field = (cells[10].inner_text() or "").strip() if len(cells) > 10 else ""
355|                    valid_as_of = (cells[11].inner_text() or "").strip() if len(cells) > 11 else ""
356|                    latest_revision = (cells[12].inner_text() or "").strip() if len(cells) > 12 else ""
357|                    
358|                    see_more_link = ""
359|                    see_more_el = cells[1].query_selector("a")
360|                    if see_more_el:
361|                        href = see_more_el.get_attribute("href") or ""
362|                        if href.startswith("/"):
363|                            href = "https://help.sap.com" + href
364|                        see_more_link = href
365|                    
366|                    impact = classify_impact(action, enablement, ref_number)
367|                    plain_english = generate_plain_english(action, enablement, title, description)
368|                    
369|                    all_items.append({
370|                        "title": title,
371|                        "description": description,
372|                        "product": product,
373|                        "module": module,
374|                        "feature": feature,
375|                        "lifecycle": lifecycle,
376|                        "action": action,
377|                        "enablement": enablement,
378|                        "refNumber": ref_number,
379|                        "demo": demo,
380|                        "version": version_field,
381|                        "validAsOf": valid_as_of,
382|                        "latestRevision": latest_revision,
383|                        "sapLink": see_more_link,
384|                        "impact": impact,
385|                        "plainEnglish": plain_english,
386|                        "releaseVersion": version_name
387|                    })
388|                    version_items += 1
389|                
390|                # After first page of a successful scrape, snapshot the first item for next version's guard
391|                if page_num == 1 and version_items > 0:
392|                    first_cell = rows[0].query_selector("td")
393|                    if first_cell:
394|                        prev_first_title = (first_cell.inner_text() or "").strip().removeprefix("Preview ")
395|                
396|                print(f"  Page {page_num}: {len(rows)} rows (total for {version_name}: {version_items})")
397|                
398|                # Next page
399|                next_btn = page.query_selector('button[title="Next page"]') or \
400|                           page.query_selector('button:has-text("")')
401|                if not next_btn:
402|                    all_btns = page.query_selector_all("button")
403|                    for btn in all_btns:
404|                        text = btn.inner_text()
405|                        if text == "" or "next" in text.lower():
406|                            next_btn = btn
407|                            break
408|                
409|                if not next_btn:
410|                    print(f"  No 'Next' button. Done with {version_name}.")
411|                    break
412|                
413|                if next_btn.get_attribute("disabled") is not None:
414|                    print(f"  Next disabled. Reached last page of {version_name}.")
415|                    break
416|                
417|                next_btn.click()
418|                page.wait_for_timeout(2000)
419|                page_num += 1
420|        
421|        browser.close()
422|    
423|    return all_items
424|
425|
426|def scrape_via_csv_download():
427|    """
428|    Alternative approach: try to download the CSV directly.
429|    The What's New Viewer has a Download Data button that can export all data.
430|    """
431|    try:
432|        from playwright.sync_api import sync_playwright
433|    except ImportError:
434|        return None
435|    
436|    items = []
437|    
438|    with sync_playwright() as p:
439|        browser = p.chromium.launch(headless=True)
440|        context = browser.new_context(accept_downloads=True)
441|        page = context.new_page()
442|        
443|        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
444|        time.sleep(3)
445|        
446|        # Try to find and click the Download button
447|        download_btn = page.query_selector('button:has-text("Download")')
448|        if download_btn:
449|            download_btn.click()
450|            time.sleep(1)
451|            
452|            # Look for XLSX or CSV option
453|            csv_btn = page.query_selector('text="XLSX"') or page.query_selector('text="CSV"')
454|            if csv_btn:
455|                # Set up download handler
456|                with page.expect_download() as download_info:
457|                    csv_btn.click()
458|                download = download_info.value
459|                path = download.path()
460|                print(f"Downloaded to: {path}")
461|                # Parse the file...
462|        
463|        browser.close()
464|    
465|    return items
466|
467|
468|def calculate_release_dates(available_versions, scraped_at=None):
469|    """
470|    Calculate estimated release dates based on SAP's typical biannual schedule.
471|
472|    SAP SuccessFactors releases follow this pattern:
473|    - 1H YYYY: Preview in April, Production in mid-May
474|    - 2H YYYY: Preview in October, Production in mid-November
475|
476|    Dates are marked as estimates if the production date is in the future
477|    relative to scraped_at. Called dynamically so new versions are handled
478|    automatically - no hardcoded year/month values needed.
479|    """
480|    if scraped_at is None:
481|        scraped_at = datetime.now()
482|
483|    release_dates = {}
484|
485|    for version in available_versions:
486|        # Normalize: strip " (Preview)" suffix for key lookup
487|        clean_version = re.sub(r'\s*\(Preview\)\s*', '', version).strip()
488|
489|        # Parse version like "1H 2026" or "2H 2026"
490|        match = re.match(r'(\d)H\s+(\d{4})', clean_version)
491|        if not match:
492|            print(f"  [WARN] Could not parse version: '{version}', skipping release dates.")
493|            continue
494|
495|        half = int(match.group(1))
496|        year = int(match.group(2))
497|
498|        if half == 1:
499|            preview_str = f"April {year}"
500|            production_str = f"May 15, {year}"
501|        else:  # 2H
502|            preview_str = f"October {year}"
503|            production_str = f"November 15, {year}"
504|
505|        # Check if production is in the future → mark as estimate
506|        try:
507|            prod_dt = datetime.strptime(production_str, "%B %d, %Y")
508|            if prod_dt > scraped_at:
509|                preview_str += " (est.)"
510|                production_str += " (est.)"
511|        except ValueError:
512|            pass
513|
514|        release_dates[clean_version] = {
515|            "preview": preview_str,
516|            "production": production_str
517|        }
518|
519|    return release_dates
520|
521|
522|def build_meta_summary(metadata: dict, items: list[dict]) -> tuple[str, str]:
523|    """Build title/description strings for HTML, Open Graph, and Twitter tags."""
524|    total = metadata.get("totalItems") or len(items)
525|    version_counts = metadata.get("versionCounts") or {}
526|    versions = list(version_counts.keys()) or metadata.get("availableVersions") or []
527|    version_text = ", ".join(versions) if versions else "the latest releases"
528|    impacts = {}
529|    for item in items:
530|        level = (item.get("impact") or {}).get("level", "low")
531|        impacts[level] = impacts.get(level, 0) + 1
532|    impact_text = ""
533|    if impacts.get("critical") or impacts.get("high"):
534|        impact_text = f" {impacts.get('critical', 0)} critical and {impacts.get('high', 0)} high impact items."
535|    refreshed = f" Last refreshed {metadata['lastScraped']}." if metadata.get("lastScraped") else ""
536|    title = f"SAP SF Release Updates - {total} SuccessFactors updates"
537|    description = (
538|        f"{total} SAP SuccessFactors release updates across {version_text}, "
539|        f"classified by impact and summarised in plain English."
540|        f"{impact_text}{refreshed}"
541|    )
542|    return title, description
543|
544|
545|def replace_meta_content(markup: str, selector_type: str, selector_value: str, content: str) -> str:
546|    escaped = html.escape(content, quote=True)
547|    pattern = rf'(<meta\s+{selector_type}="{re.escape(selector_value)}"\s+content=")[^"]*(">)'
548|    replacement = rf"\g<1>{escaped}\2"
549|    updated, count = re.subn(pattern, replacement, markup, count=1)
550|    if count:
551|        return updated
552|    insert_after = '<meta name="twitter:card" content="summary_large_image">' if selector_type == "name" and selector_value.startswith("twitter:") else '<meta property="og:url" content="https://sahirvhora.github.io/sf-release-update/">'
553|    tag = f'<meta {selector_type}="{selector_value}" content="{escaped}">'
554|    return updated.replace(insert_after, insert_after + "\n" + tag, 1)
555|
556|
557|def update_index_metadata(output: dict) -> None:
558|    if not INDEX_FILE.exists():
559|        print("[WARN] index.html missing; skipping static meta update.")
560|        return
561|    title, description = build_meta_summary(output["metadata"], output["items"])
562|    markup = INDEX_FILE.read_text(encoding="utf-8")
563|    markup = replace_meta_content(markup, "property", "og:title", title)
564|    markup = replace_meta_content(markup, "property", "og:description", description)
565|    markup = replace_meta_content(markup, "name", "twitter:title", title)
566|    markup = replace_meta_content(markup, "name", "twitter:description", description)
567|    markup = replace_meta_content(markup, "name", "description", description)
568|    title_escaped = html.escape(title, quote=False)
569|    markup = re.sub(r"<title>.*?</title>", f"<title>{title_escaped}</title>", markup, count=1, flags=re.DOTALL)
570|    INDEX_FILE.write_text(markup, encoding="utf-8")
571|    print(f"Updated static index.html metadata: {title}")
572|
573|
574|def main():
575|    print("=" * 60)
576|    print("SAP SF Release Updates - Scraper")
577|    print(f"Target: {BASE_URL}")
578|    print(f"Time: {datetime.now().isoformat()}")
579|    print("=" * 60)
580|    
581|    # Try Playwright extraction
582|    items = scrape_with_playwright()
583|    
584|    if not items:
585|        print("ERROR: No items extracted. Check the SAP page structure.")
586|        sys.exit(1)
587|    
588|    # Deduplicate by title + refNumber across all versions.
589|    # When the same deprecation/change appears in both 1H and 2H, keep only the
590|    # first occurrence (earliest version, since we scrape 1H before 2H).
591|    seen = set()
592|    unique = []
593|    for item in items:
594|        key = (item["title"], item.get("refNumber", ""))
595|        if key not in seen:
596|            seen.add(key)
597|            unique.append(item)
598|    
599|    print(f"\nTotal extracted: {len(items)}")
600|    print(f"After dedup: {len(unique)}")
601|    
602|    # Count by impact
603|    impact_counts = {}
604|    for item in unique:
605|        level = item["impact"]["level"]
606|        impact_counts[level] = impact_counts.get(level, 0) + 1
607|    print(f"Impact breakdown: {impact_counts}")
608|    
609|    # Count by module
610|    module_counts = {}
611|    for item in unique:
612|        mod = item["module"] or "Unknown"
613|        module_counts[mod] = module_counts.get(mod, 0) + 1
614|    print(f"Top modules: {dict(sorted(module_counts.items(), key=lambda x: -x[1])[:10])}")
615|    
616|    # Count by version
617|    version_counts = {}
618|    for item in unique:
619|        ver = item.get("releaseVersion", "Unknown")
620|        version_counts[ver] = version_counts.get(ver, 0) + 1
621|    print(f"Version breakdown: {version_counts}")
622|    
623|    # Build output
624|    available_versions = sorted(set(item.get("releaseVersion", "Unknown") for item in unique))
625|    scraped_at = datetime.now()
626|    release_dates = calculate_release_dates(available_versions, scraped_at)
627|    output = {
628|        "metadata": {
629|            "source": BASE_URL,
630|            "scrapedAt": scraped_at.isoformat(),
631|            "totalItems": len(unique),
632|            "lastScraped": scraped_at.strftime("%Y-%m-%d %H:%M UTC"),
633|            "availableVersions": available_versions,
634|            "versionCounts": version_counts,
635|            "releaseDates": release_dates
636|        },
637|        "items": unique
638|    }
639|    
640|    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
641|    with open(OUTPUT_FILE, "w") as f:
642|        json.dump(output, f, indent=2, ensure_ascii=False)
643|    update_index_metadata(output)
644|    
645|    print(f"\nSaved {len(unique)} items to {OUTPUT_FILE}")
646|    print("Done!")
647|
648|
649|if __name__ == "__main__":
650|    main()
651|