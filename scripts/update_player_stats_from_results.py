"""公開済み結果からplayer_stats.jsonを増分更新する。"""
import json
import os
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "scripts" / "data"
STATS_PATH = ROOT_DIR / "player_stats.json"
STATE_PATH = ROOT_DIR / "player_stats_updates.json"

BANK_LENGTH = {
    "函館": 400, "青森": 400, "いわき平": 400,
    "弥彦": 400, "前橋": 335, "取手": 400, "宇都宮": 500,
    "大宮": 500, "西武園": 400, "京王閣": 400, "立川": 400,
    "松戸": 333, "千葉": 500, "川崎": 400, "平塚": 400,
    "小田原": 333, "伊東": 333, "静岡": 400,
    "名古屋": 400, "岐阜": 400, "大垣": 400, "豊橋": 400,
    "富山": 333, "松阪": 400, "四日市": 400,
    "福井": 400, "奈良": 333, "向日町": 400, "和歌山": 400, "岸和田": 400,
    "玉野": 400, "広島": 400, "防府": 333,
    "高松": 400, "小松島": 400, "高知": 500, "松山": 400,
    "小倉": 400, "久留米": 400, "武雄": 400, "佐世保": 400,
    "別府": 400, "熊本": 500,
}


def load_json(path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, payload):
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def bank_key(venue):
    bank = BANK_LENGTH.get(venue, 400)
    if bank <= 335:
        return "s"
    if bank >= 500:
        return "l"
    return "m"


def form_score(ranks):
    if not ranks:
        return 0
    weights = [1.0, 0.92, 0.84, 0.76, 0.68, 0.60, 0.52, 0.44, 0.36, 0.28]
    total = 0.0
    denom = 0.0
    for rank, weight in zip(ranks[:10], weights):
        total += max(0, 8 - int(rank)) * weight
        denom += 7 * weight
    return round(total / max(0.001, denom) * 10, 1)


def entry_index(date_str):
    path = ROOT_DIR / f"entries_{date_str}.json"
    if not path.exists():
        path = DATA_DIR / f"entries_{date_str}.json"
    payload = load_json(path, {})
    index = {}
    for race in payload.get("races") or []:
        for entry in race.get("entries") or []:
            index[(race.get("race_id"), entry.get("umaban"))] = entry
    return index


def default_player(entry=None):
    entry = entry or {}
    return {
        "d": "",
        "p": "",
        "s": entry.get("style") or "",
        "c": "",
        "g": 0,
        "r": 0,
        "w": 0,
        "wr": 0,
        "t2": 0,
        "t3": 0,
        "rr": [],
        "rk": [],
        "vs": {},
        "bk": {},
        "fm": 0,
        "dk": "",
    }


def update_player(player, venue, rank, kimarite, entry):
    old_races = int(player.get("r") or 0)
    old_wins = int(player.get("w") or 0)
    old_top2 = round(float(player.get("t2") or 0) * old_races)
    old_top3 = round(float(player.get("t3") or 0) * old_races)

    new_races = old_races + 1
    new_wins = old_wins + (1 if rank == 1 else 0)
    new_top2 = old_top2 + (1 if rank <= 2 else 0)
    new_top3 = old_top3 + (1 if rank <= 3 else 0)

    player["r"] = new_races
    player["w"] = new_wins
    player["wr"] = round(new_wins / new_races, 4)
    player["t2"] = round(new_top2 / new_races, 4)
    player["t3"] = round(new_top3 / new_races, 4)

    if entry and entry.get("style"):
        player["s"] = entry.get("style")

    player["rr"] = ([rank] + [int(x) for x in player.get("rr", [])])[:10]
    if kimarite:
        player["rk"] = ([kimarite] + list(player.get("rk", [])))[:10]
    else:
        player["rk"] = list(player.get("rk", []))[:10]

    venue_stats = dict(player.get("vs") or {})
    venue_record = dict(venue_stats.get(venue) or {"r": 0, "w": 0})
    venue_record["r"] = int(venue_record.get("r") or 0) + 1
    venue_record["w"] = int(venue_record.get("w") or 0) + (1 if rank == 1 else 0)
    venue_stats[venue] = venue_record
    player["vs"] = venue_stats

    banks = dict(player.get("bk") or {})
    key = bank_key(venue)
    bank_record = dict(banks.get(key) or {"r": 0, "w": 0, "t3": 0})
    bank_record["r"] = int(bank_record.get("r") or 0) + 1
    bank_record["w"] = int(bank_record.get("w") or 0) + (1 if rank == 1 else 0)
    bank_record["t3"] = int(bank_record.get("t3") or 0) + (1 if rank <= 3 else 0)
    banks[key] = bank_record
    player["bk"] = banks

    player["fm"] = form_score(player["rr"])
    kimarite_counts = Counter(k for k in player.get("rk", []) if k)
    player["dk"] = kimarite_counts.most_common(1)[0][0] if kimarite_counts else player.get("dk", "")
    return player


def update_from_result_file(result_path):
    stats = load_json(STATS_PATH, {})
    state = load_json(STATE_PATH, {"processed_dates": []})
    processed = set(state.get("processed_dates") or [])

    payload = load_json(result_path, {})
    date_str = payload.get("date")
    if not date_str or date_str in processed:
        print(f"player_stats: skip {date_str or result_path.name}")
        return False

    entries = entry_index(date_str)
    changed = 0
    for race in payload.get("results") or []:
        venue = race.get("venue") or ""
        for finisher in race.get("finishers") or []:
            rank = int(finisher.get("rank") or 0)
            name = finisher.get("name") or ""
            umaban = int(finisher.get("umaban") or 0)
            if not name or rank <= 0:
                continue
            entry = entries.get((race.get("race_id"), umaban), {})
            player = dict(stats.get(name) or default_player(entry))
            stats[name] = update_player(player, venue, rank, finisher.get("kimarite") or "", entry)
            changed += 1

    if changed == 0:
        print(f"player_stats: no finishers for {date_str}")
        return False

    state["processed_dates"] = sorted(processed | {date_str})
    save_json(STATS_PATH, stats)
    save_json(STATE_PATH, state)
    print(f"player_stats: updated {changed} finishers for {date_str}")
    return True


def main():
    result_files = sorted(DATA_DIR.glob("results_*.json")) + sorted(ROOT_DIR.glob("results_*.json"))
    if not result_files and (DATA_DIR / "today_results.json").exists():
        result_files = [DATA_DIR / "today_results.json"]
    changed = False
    for path in result_files:
        changed = update_from_result_file(path) or changed
    if not changed:
        print("player_stats: no updates")


if __name__ == "__main__":
    main()
