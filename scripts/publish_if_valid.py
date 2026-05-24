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

    if not valid_entry_file(today_path, today):
        print("entries: invalid or empty today_entries.json; keeping previous published data")
        raise SystemExit(1)

    upcoming = load_json(upcoming_path) if upcoming_path.exists() else {}
    upcoming_races = upcoming.get("races", [])
    if not upcoming_races or not any(r.get("date") == today and r.get("entries") for r in upcoming_races):
        print("entries: invalid or empty upcoming_entries.json; keeping previous published data")
        raise SystemExit(1)

    copy_if_exists("today_entries.json")
    copy_if_exists("upcoming_entries.json")
    for path in DATA_DIR.glob("entries_*.json"):
        shutil.copyfile(path, ROOT_DIR / path.name)
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
