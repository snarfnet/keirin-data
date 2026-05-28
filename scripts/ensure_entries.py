"""netkeibaが失敗した時にDMMへ自動フォールバックして出走表を公開する。"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import publish_if_valid
import scrape_entries
import scrape_entries_dmm

DATA_DIR = Path(__file__).resolve().parent / "data"
TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def is_valid_today():
    today = datetime.now(TOKYO_TZ).strftime("%Y%m%d")
    path = DATA_DIR / "today_entries.json"
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as f:
        payload = json.load(f)
    races = payload.get("races") or []
    return payload.get("date") == today and any(race.get("entries") for race in races)


def clear_fresh_files():
    for name in ("today_entries.json", "upcoming_entries.json"):
        path = DATA_DIR / name
        if path.exists():
            path.unlink()


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("GitHub Actions detected. primary: DMM")
        clear_fresh_files()
        scrape_entries_dmm.scrape_entries(days)
        publish_if_valid.publish_entries()
        return

    print("primary: netkeiba")
    clear_fresh_files()
    scrape_entries.scrape_entries(days)

    if not is_valid_today():
        print("primary empty. fallback: DMM")
        clear_fresh_files()
        scrape_entries_dmm.scrape_entries(days)

    publish_if_valid.publish_entries()


if __name__ == "__main__":
    main()
