#!/usr/bin/env bash
# pipeline.sh — pipeline post-scraping.
#
# El scraping en sí lo hace Friday (cron diario "scrape-inmobiliaria"
# en cron-prompts.md §24) lanzando agentes Task en paralelo. Este script
# corre DESPUÉS, para:
#   1. validar links (HEAD a cada offer.link)
#   2. commit + push si hubo cambios en data/

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

LOG="/tmp/inmobiliaria-pipeline-$(date +%Y%m%d-%H%M).log"
echo "=== pipeline $(date -Iseconds) ===" | tee "$LOG"

echo "[1/2] validating links…" | tee -a "$LOG"
python3 backend/validator.py 2>&1 | tee -a "$LOG" || {
  echo "validator failed, continuing" | tee -a "$LOG"
}

echo "[2/2] commit + push…" | tee -a "$LOG"
if git diff --quiet data/; then
  echo "no data changes, skipping commit" | tee -a "$LOG"
else
  git add data/ assets/images/ 2>/dev/null || true
  count=$(jq 'length' data/offers.json 2>/dev/null || echo 0)
  git commit -m "chore: refresh offers ($count listings, $(date -u +%Y-%m-%d))" 2>&1 | tee -a "$LOG"
  if git remote get-url origin >/dev/null 2>&1; then
    git push origin HEAD 2>&1 | tee -a "$LOG"
  else
    echo "no remote configured, skip push" | tee -a "$LOG"
  fi
fi

echo "=== done $(date -Iseconds) ===" | tee -a "$LOG"
