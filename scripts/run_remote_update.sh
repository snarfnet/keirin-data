#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-entries}"
BRANCH="${KEIRIN_GIT_BRANCH:-main}"
DAYS_AHEAD="${KEIRIN_DAYS_AHEAD:-1}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REMOTE_URL="${KEIRIN_GIT_REMOTE_URL:-}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

ensure_git_ready() {
  if [[ -n "$REMOTE_URL" ]]; then
    git remote set-url origin "$REMOTE_URL"
  fi

  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
}

ensure_python_ready() {
  if [[ ! -d ".venv" ]]; then
    "$PYTHON_BIN" -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt

  if [[ ! -f ".venv/.playwright-chromium-installed" ]]; then
    python -m playwright install chromium
    touch .venv/.playwright-chromium-installed
  fi
}

run_entries() {
  log "Scraping entries"
  (
    cd scripts
    mkdir -p data
    python -u scrape_entries.py "$DAYS_AHEAD"
    python -u publish_if_valid.py entries
  )
}

run_odds() {
  log "Scraping odds"
  (
    cd scripts
    mkdir -p data
    python -u scrape_odds.py
    python -u publish_if_valid.py odds
  )
}

run_results() {
  log "Scraping results"
  (
    cd scripts
    mkdir -p data
    result_date="$(python - <<'PY'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("Asia/Tokyo"))
target = now if now.hour >= 21 else now - timedelta(days=1)
print(target.strftime("%Y%m%d"))
PY
)"
    python -u scraper.py "$result_date" "$result_date"
    python -u scrape_results.py "$result_date"
    python -u publish_if_valid.py results
  )
}

commit_and_push() {
  git add *.json
  if git diff --cached --quiet; then
    log "No JSON changes to publish"
    return
  fi

  git config user.name "${GIT_AUTHOR_NAME:-keirin-data-bot}"
  git config user.email "${GIT_AUTHOR_EMAIL:-keirin-data-bot@example.local}"
  git commit -m "Remote update: $(date -u +%Y%m%d-%H%M)"
  git push origin "$BRANCH"
}

main() {
  ensure_git_ready
  ensure_python_ready

  case "$MODE" in
    entries)
      run_entries
      ;;
    all)
      run_entries
      run_odds || log "Odds update failed; keeping previous odds"
      run_results || log "Results update failed; keeping previous results"
      ;;
    *)
      echo "usage: $0 [entries|all]" >&2
      exit 2
      ;;
  esac

  commit_and_push
  log "Done"
}

main "$@"
