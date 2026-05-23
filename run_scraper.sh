#!/usr/bin/env bash
# run_scraper.sh — Run the SAP SF release scraper and commit any changes.
# Designed to be called from GitHub Actions on a cron schedule.
set -euo pipefail

cd "$(dirname "$0")"

echo "=== Running SAP SF Release Scraper ==="

# Run the scraper
python3 scraper.py

# Check if the data file changed
if git diff --quiet data/updates.json; then
    echo "No changes to updates.json — nothing to commit."
    exit 0
fi

echo "Data changed! Committing and pushing..."

# Configure git (GitHub Actions sets these, but set defaults for local use)
git config user.name  "${GIT_USER_NAME:-SAP Release Bot}"
git config user.email "${GIT_USER_EMAIL:-release-bot@sf-release-update.github}"

# Stage and commit
git add data/updates.json

COMMIT_MSG="chore: auto-update release data ($(date -u +'%Y-%m-%d'))"
git commit -m "$COMMIT_MSG"

# Pull latest to avoid non-fast-forward rejections (e.g., if another commit landed)
git pull --rebase origin "${GITHUB_REF_NAME:-$(git branch --show-current)}" || true

# Push
git push

echo "=== Done! Changes pushed. ==="
