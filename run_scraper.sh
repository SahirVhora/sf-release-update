#!/usr/bin/env bash
# run_scraper.sh - Run the SAP SF release scraper and commit any changes.
# Designed to be called from GitHub Actions on a cron schedule.
# Sends Telegram alerts on failure or when new data is found.
set -euo pipefail

cd "$(dirname "$0")"

# ── Telegram notification helper ──────────────────────────────────────────
# Uses the same TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID secrets as daily-news-bot.
# No-op when env vars are unset (e.g. local runs).
send_telegram() {
    local message="$1"
    local token="${TELEGRAM_BOT_TOKEN:-}"
    local chat_id="${TELEGRAM_CHAT_ID:-}"

    if [[ -z "$token" || -z "$chat_id" ]]; then
        echo "[telegram] Skipping - TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set."
        return 0
    fi

    local url="https://api.telegram.org/bot${token}/sendMessage"
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$url" \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "import json,sys; print(json.dumps({'chat_id':sys.argv[1],'text':sys.argv[2]}))" "$chat_id" "$message")" \
        2>/dev/null || echo "000")

    if [[ "$http_code" == "200" ]]; then
        echo "[telegram] Notification sent."
    else
        echo "[telegram] WARNING: send failed (HTTP $http_code). Continuing anyway."
    fi
}

# ── Build a GitHub Actions run URL (empty if not in CI) ───────────────────
ci_run_url() {
    local server="${GITHUB_SERVER_URL:-https://github.com}"
    local repo="${GITHUB_REPOSITORY:-}"
    local run_id="${GITHUB_RUN_ID:-}"
    if [[ -n "$repo" && -n "$run_id" ]]; then
        echo "$server/$repo/actions/runs/$run_id"
    else
        echo ""
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────

echo "=== Running SAP SF Release Scraper ==="

# Run the scraper.  set -e is on, so any non-zero exit kills the script.
# We trap the exit so we can send a Telegram alert before dying.
trap 'SCRAPER_EXIT=$?; if [[ $SCRAPER_EXIT -ne 0 ]]; then
  RUN_URL=$(ci_run_url)
  MSG="❌ SAP SF scraper FAILED (exit code $SCRAPER_EXIT)."$'\n'"Check the logs to diagnose."
  if [[ -n "$RUN_URL" ]]; then MSG="$MSG"$'\n'"$RUN_URL"; fi
  send_telegram "$MSG"
fi; exit $SCRAPER_EXIT' EXIT

python3 scraper.py

# If we got here, the scraper succeeded (exit 0).  Clear the trap.
trap - EXIT

# Check if the data file changed
if git diff --quiet data/updates.json index.html; then
    echo "No changes to updates.json or index.html - nothing to commit."

    # Send an info notification on Mondays so we know the cron is alive.
    # Avoid spamming every day - only notify if it's a Monday (UTC).
    if [[ "$(date -u +%u)" == "1" ]]; then
        RUN_URL=$(ci_run_url)
        MSG="🟢 SAP SF scraper ran successfully - no new updates this week."
        if [[ -n "$RUN_URL" ]]; then
            MSG="$MSG"$'\n'"$RUN_URL"
        fi
        send_telegram "$MSG"
    fi
    exit 0
fi

echo "Data changed! Committing and pushing..."

# Configure git (GitHub Actions sets these, but set defaults for local use)
git config user.name  "${GIT_USER_NAME:-SAP Release Bot}"
git config user.email "${GIT_USER_EMAIL:-release-bot@sf-release-update.github}"

# Stage and commit
# data/ is ignored for local scratch files, so force-add the tracked release JSON.
git add -f data/updates.json index.html

COMMIT_MSG="chore: auto-update release data ($(date -u +'%Y-%m-%d'))"
git commit -m "$COMMIT_MSG"

# Pull latest to avoid non-fast-forward rejections (e.g., if another commit landed)
git pull --rebase origin "${GITHUB_REF_NAME:-$(git branch --show-current)}" || true

# Push
git push

echo "=== Done! Changes pushed. ==="

# ── Success notification ──────────────────────────────────────────────────
# Extract a summary from the updated JSON for the Telegram alert.
SUMMARY=$(python3 -c "
import json
with open('data/updates.json') as f:
    d = json.load(f)
m = d['metadata']
vc = m.get('versionCounts', {})
impacts = {}
for item in d['items']:
    lvl = item['impact']['level']
    impacts[lvl] = impacts.get(lvl, 0) + 1

parts = [f'Total items: {len(d[\"items\"])}']
for v, c in vc.items():
    parts.append(f'{v}: {c} items')
parts.append(f'Impact: {impacts.get(\"critical\",0)} critical, {impacts.get(\"high\",0)} high, {impacts.get(\"medium\",0)} medium, {impacts.get(\"low\",0)} low')
print(' | '.join(parts))
" 2>/dev/null || echo "(unable to read summary)")

RUN_URL=$(ci_run_url)

MSG="✅ SAP SF Release data updated!"$'\n'"$SUMMARY"
if [[ -n "$RUN_URL" ]]; then
    MSG="$MSG"$'\n'"$RUN_URL"
fi
send_telegram "$MSG"
