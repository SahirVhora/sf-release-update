#!/usr/bin/env python3
"""
SF Update Pulse — Scraper
Fetches the latest SAP SuccessFactors What's New data and outputs structured JSON.
Run: python3 scraper.py
Output: data/updates.json
"""

import json, os, re, sys, time
from datetime import datetime
from pathlib import Path

# --- Config ---
BASE_URL = "https://help.sap.com/whats-new/8fcf4960eea24f78b1d7613da406a885"
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "updates.json"
# How many pages to fetch (25 items per page). Set high, script stops when no more data.
MAX_PAGES = 50

# --- Impact Classification ---
# Impact = f(Action, Enablement)
def classify_impact(action: str, enablement: str, ref_number: str = "") -> dict:
    """Return impact level and label based on SAP's Action + Enablement columns.
    SAP quirk: deprecated items often have action='Changed' with refNumber='Deprecated'."""
    action = (action or "").strip().lower()
    enablement = (enablement or "").strip().lower()
    ref_number = (ref_number or "").strip().lower()
    
    # Detect deprecation from either the action field or the reference number
    is_deprecated = action in ("deprecated", "deleted") or ref_number == "deprecated"
    
    if is_deprecated:
        if enablement in ("required", "automatically on", ""):
            return {"level": "critical", "label": "Critical", "color": "#ef4444"}
        return {"level": "high", "label": "High", "color": "#f97316"}
    
    # High: Major enablement changes or forced changes
    if enablement == "major":
        return {"level": "high", "label": "High", "color": "#f97316"}
    if action == "changed" and enablement in ("required", "automatically on"):
        return {"level": "high", "label": "High", "color": "#f97316"}
    
    # Medium: Changes needing config or new major features
    if action == "changed" and enablement in ("minor", "customer configured"):
        return {"level": "medium", "label": "Medium", "color": "#eab308"}
    if action == "new" and enablement == "major":
        return {"level": "medium", "label": "Medium", "color": "#eab308"}
    
    # Low: Everything else
    return {"level": "low", "label": "Low", "color": "#22c55e"}


def generate_plain_english(action: str, enablement: str, title: str, description: str) -> str:
    """Generate a contextual plain-English summary incorporating title and description details."""
    action = (action or "").strip().lower()
    enablement = (enablement or "").strip().lower()
    
    # Extract first sentence for context
    first_sentence = description.split(".")[0].strip() if description else ""
    # Shorten very long sentences
    if len(first_sentence) > 200:
        first_sentence = first_sentence[:197] + "..."
    
    # Extract dates if present
    import re
    dates = re.findall(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', description)
    date_str = ""
    if dates:
        # Find full date match (not just captured month group)
        full_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', description)
        if full_match:
            date_str = f" Timeline: {full_match.group(0)}."
    
    # Detect urgency words
    urgent_words = ["deleted", "removed", "no longer available", "end of", "must", "required"]
    is_urgent = any(w in description.lower() for w in urgent_words)
    
    if action == "deprecated" or (action == "changed" and "deprecated" in description.lower()):
        if is_urgent:
            return f"Will stop working - you need a replacement.{date_str} Check the linked SAP Note for migration steps."
        return f"Being phased out. Start planning your move to the replacement now.{date_str}"
    
    if action == "deleted":
        return f"Already removed. If you relied on this, switch to the alternative immediately.{date_str}"
    
    if action == "new":
        if enablement == "major":
            return f"Significant new capability - could change how you work. {first_sentence} Review config steps and test in sandbox first."
        if enablement in ("minor", "customer configured"):
            return f"Available when you're ready. {first_sentence} Test in non-production before enabling broadly."
        return f"Active automatically - no setup needed. {first_sentence}"
    
    if action == "changed":
        if is_urgent:
            return f"Important change you need to act on.{date_str} Review the details - this affects your system automatically."
        if enablement == "major":
            return f"Significant update. {first_sentence} Plan configuration changes and communicate to users."
        if enablement in ("minor", "customer configured"):
            return f"Minor update - configure if useful. {first_sentence}"
        return f"Updated automatically. {first_sentence}"
    
    # Fallback with context
    return f"Review this change. {first_sentence}"


# --- Scraping ---
def scrape_with_playwright():
    """Use Playwright to extract all rows from the What's New Viewer."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)
    
    all_items = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage'
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        # Hide automation
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)
        page = context.new_page()
        
        print(f"Loading {BASE_URL} ...")
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=120000)
        except Exception as e:
            print(f"Initial load warning: {e}. Trying load event...")
            page.goto(BASE_URL, wait_until="load", timeout=120000)
        
        # Dismiss cookie consent banner if present (TrustArc)
        print("Checking for cookie consent banner...")
        try:
            consent_btn = page.wait_for_selector(
                'button:has-text("Accept All"), button:has-text("Accept Cookies"), '
                'button:has-text("OK"), button#truste-consent-button, '
                'a:has-text("Accept All"), .trustarc-agree-btn',
                timeout=15000
            )
            if consent_btn:
                print("Dismissing cookie consent banner...")
                consent_btn.click()
                page.wait_for_timeout(2000)
        except:
            print("No cookie consent banner found (or already accepted).")
        
        # Also try clicking away any overlay
        try:
            page.evaluate("""
                const banners = document.querySelectorAll('#truste-consent-track, .trustarc-banner, [id*="consent_blackbar"]');
                banners.forEach(b => b.style.display = 'none');
            """)
        except:
            pass
        
        # Wait for Vue to render — look for the table or filters
        print("Waiting for page to render...")
        try:
            page.wait_for_selector("table tbody tr, button:has-text('Product')", timeout=45000)
        except:
            print("WARNING: Selectors not found. Page might not have loaded fully.")
        
        # Extra wait for Vue hydration
        page.wait_for_timeout(5000)
        
        page_num = 1
        while page_num <= MAX_PAGES:
            # Extract rows from current page
            rows = page.query_selector_all("table tbody tr")
            if not rows:
                print(f"No rows found on page {page_num}. Stopping.")
                break
            
            for row in rows:
                cells = row.query_selector_all("td")
                if len(cells) < 8:
                    continue
                
                title = (cells[0].inner_text() or "").strip().removeprefix("Preview ")
                description = (cells[1].inner_text() or "").strip().removesuffix("See More").strip()
                product = (cells[2].inner_text() or "").strip()
                # Module may span multiple lines — take first line only (primary module)
                module_raw = (cells[3].inner_text() or "").strip()
                module = module_raw.split("\n")[0].strip()
                feature = (cells[4].inner_text() or "").strip()
                lifecycle = (cells[5].inner_text() or "").strip()
                action = (cells[6].inner_text() or "").strip()
                enablement = (cells[7].inner_text() or "").strip()
                ref_number = (cells[8].inner_text() or "").strip() if len(cells) > 8 else ""
                demo = (cells[9].inner_text() or "").strip() if len(cells) > 9 else ""
                version = (cells[10].inner_text() or "").strip() if len(cells) > 10 else ""
                valid_as_of = (cells[11].inner_text() or "").strip() if len(cells) > 11 else ""
                latest_revision = (cells[12].inner_text() or "").strip() if len(cells) > 12 else ""
                
                # Get the "See More" link if available and make it absolute
                see_more_link = ""
                see_more_el = cells[1].query_selector("a")
                if see_more_el:
                    href = see_more_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = "https://help.sap.com" + href
                    see_more_link = href
                
                impact = classify_impact(action, enablement, ref_number)
                plain_english = generate_plain_english(action, enablement, title, description)
                
                all_items.append({
                    "title": title,
                    "description": description,
                    "product": product,
                    "module": module,
                    "feature": feature,
                    "lifecycle": lifecycle,
                    "action": action,
                    "enablement": enablement,
                    "refNumber": ref_number,
                    "demo": demo,
                    "version": version,
                    "validAsOf": valid_as_of,
                    "latestRevision": latest_revision,
                    "sapLink": see_more_link,
                    "impact": impact,
                    "plainEnglish": plain_english
                })
            
            print(f"Page {page_num}: extracted {len(rows)} rows (total: {len(all_items)})")
            
            # Try to click "Next" page button
            next_btn = page.query_selector('button[title="Next page"]') or \
                       page.query_selector('button:has-text("")')
            
            # Try various next-page selectors
            if not next_btn:
                # Look for pagination buttons
                all_btns = page.query_selector_all("button")
                for btn in all_btns:
                    text = btn.inner_text()
                    if text == "" or "next" in text.lower():
                        next_btn = btn
                        break
            
            if not next_btn:
                print("No 'Next' button found. Assuming last page.")
                break
            
            # Check if disabled
            is_disabled = next_btn.get_attribute("disabled") is not None
            if is_disabled:
                print("Next button is disabled. Reached last page.")
                break
            
            next_btn.click()
            time.sleep(2)  # Wait for page transition
            page_num += 1
        
        browser.close()
    
    return all_items


def scrape_via_csv_download():
    """
    Alternative approach: try to download the CSV directly.
    The What's New Viewer has a Download Data button that can export all data.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    
    items = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        time.sleep(3)
        
        # Try to find and click the Download button
        download_btn = page.query_selector('button:has-text("Download")')
        if download_btn:
            download_btn.click()
            time.sleep(1)
            
            # Look for XLSX or CSV option
            csv_btn = page.query_selector('text="XLSX"') or page.query_selector('text="CSV"')
            if csv_btn:
                # Set up download handler
                with page.expect_download() as download_info:
                    csv_btn.click()
                download = download_info.value
                path = download.path()
                print(f"Downloaded to: {path}")
                # Parse the file...
        
        browser.close()
    
    return items


def main():
    print("=" * 60)
    print("SF Update Pulse — Scraper")
    print(f"Target: {BASE_URL}")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 60)
    
    # Try Playwright extraction
    items = scrape_with_playwright()
    
    if not items:
        print("ERROR: No items extracted. Check the SAP page structure.")
        sys.exit(1)
    
    # Deduplicate by title + refNumber
    seen = set()
    unique = []
    for item in items:
        key = (item["title"], item.get("refNumber", ""))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    print(f"\nTotal extracted: {len(items)}")
    print(f"After dedup: {len(unique)}")
    
    # Count by impact
    impact_counts = {}
    for item in unique:
        level = item["impact"]["level"]
        impact_counts[level] = impact_counts.get(level, 0) + 1
    print(f"Impact breakdown: {impact_counts}")
    
    # Count by module
    module_counts = {}
    for item in unique:
        mod = item["module"] or "Unknown"
        module_counts[mod] = module_counts.get(mod, 0) + 1
    print(f"Top modules: {dict(sorted(module_counts.items(), key=lambda x: -x[1])[:10])}")
    
    # Build output
    output = {
        "metadata": {
            "source": BASE_URL,
            "scrapedAt": datetime.now().isoformat(),
            "totalItems": len(unique),
            "lastScraped": datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        },
        "items": unique
    }
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(unique)} items to {OUTPUT_FILE}")
    print("Done!")


if __name__ == "__main__":
    main()
