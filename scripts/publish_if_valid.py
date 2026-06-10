"""Validate freshly scraped files before publishing them to the repo root."""
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path(__file__).resolve().parent / "data"
ROOT_DIR = Path(__file__).resolve().parent.parent
TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def load_json(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def copy_if_exists(src_name, dst_name=None):
    src = DATA_DIR / src_name
    if src.exists():
        shutil.copyfile(src, ROOT_DIR / (dst_name or src_name))


def valid_entry_file(path, expected_date):
    if not path.exists():
        return False
    payload = load_json(path)
    races = payload.get("races", [])
    if payload.get("date") != expected_date or not races:
        return False
    return any(race.get("entries") for race in races)


def publish_entries():
    today = datetime.now(TOKYO_TZ).strftime("%Y%m%d")
    today_path = DATA_DIR / "today_entries.json"
    upcoming_path = DATA_DIR / "upcoming_entries.json"
    root_today_path = ROOT_DIR / "today_entries.json"
    root_upcoming_path = ROOT_DIR / "upcoming_entries.json"

    if not valid_entry_file(today_path, today):
        if valid_entry_file(root_today_path, today):
            print("entries: scraped data empty, but published today_entries.json is already current")
            return
        print("entries: invalid or empty today_entries.json; keeping previous published data")
        raise SystemExit(1)

    upcoming = load_json(upcoming_path) if upcoming_path.exists() else {}
    upcoming_races = upcoming.get("races", [])
    upcoming_ok = (
        upcoming.get("date") == today
        and upcoming_races
        and any(r.get("date") == today and r.get("entries") for r in upcoming_races)
    )
    if not upcoming_ok:
        root_upcoming = load_json(root_upcoming_path) if root_upcoming_path.exists() else {}
        root_races = root_upcoming.get("races", [])
        root_upcoming_ok = (
            root_upcoming.get("date") == today
            and any(r.get("date") == today and r.get("entries") for r in root_races)
        )
        if root_upcoming_ok:
            print("entries: scraped upcoming empty, but published upcoming_entries.json is already current")
            return
        print("entries: invalid or empty upcoming_entries.json; keeping previous published data")
        raise SystemExit(1)

    copy_if_exists("today_entries.json")
    copy_if_exists("upcoming_entries.json")
    publish_dates = set(upcoming.get("days") or [])
    if not publish_dates:
        publish_dates.add(today)
    for date_str in sorted(publish_dates):
        copy_if_exists(f"entries_{date_str}.json")
    print("entries: published")


def publish_results():
    result_path = DATA_DIR / "today_results.json"
    if not result_path.exists():
        print("results: missing today_results.json; keeping previous published data")
        return
    payload = load_json(result_path)
    if not payload.get("results"):
        print("results: empty today_results.json; keeping previous published data")
        return
    copy_if_exists("today_results.json")
    date_str = payload.get("date")
    if date_str:
        dated_name = f"results_{date_str}.json"
        dated_path = DATA_DIR / dated_name
        if dated_path.exists():
            copy_if_exists(dated_name)
    print("results: published")


def publish_odds():
    odds_path = DATA_DIR / "today_odds.json"
    if not odds_path.exists():
        print("odds: missing today_odds.json; keeping previous published data")
        return
    payload = load_json(odds_path)
    if not payload.get("races"):
        print("odds: empty today_odds.json; keeping previous published data")
        return
    copy_if_exists("today_odds.json")
    print("odds: published")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "entries":
        publish_entries()
    elif mode == "results":
        publish_results()
    elif mode == "odds":
        publish_odds()
    else:
        raise SystemExit("usage: publish_if_valid.py entries|results|odds")
