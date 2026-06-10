"""DMM競輪GraphQLから出走表を取得するフォールバック。"""
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKYO_TZ = ZoneInfo("Asia/Tokyo")
DMM_GRAPHQL_URL = "https://api.keirin.dmm.com/v1/graphql/query"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://keirin.dmm.com",
    "Referer": "https://keirin.dmm.com/racecard",
}

VENUE_CODES = {
    "11": "函館", "12": "青森", "13": "いわき平",
    "21": "弥彦", "22": "前橋", "23": "取手", "24": "宇都宮",
    "25": "大宮", "26": "西武園", "27": "京王閣", "28": "立川",
    "31": "松戸", "32": "千葉", "34": "川崎", "35": "平塚",
    "36": "小田原", "37": "伊東", "38": "静岡",
    "42": "名古屋", "43": "岐阜", "44": "大垣", "45": "豊橋",
    "46": "富山", "47": "松阪", "48": "四日市",
    "51": "福井", "53": "奈良", "54": "向日町", "55": "和歌山", "56": "岸和田",
    "61": "玉野", "62": "広島", "63": "防府",
    "71": "高松", "72": "小松島", "73": "高知", "75": "松山",
    "81": "小倉", "83": "久留米", "84": "武雄", "85": "佐世保",
    "86": "別府", "87": "熊本",
}

PROGRAMS_QUERY = """
query GetRacePrograms($input: raceProgramsInput!) {
  racePrograms(input: $input) {
    id
    velodromeCode
    heldDate
    raceCount
  }
}
"""

PROGRAM_QUERY = """
query GetRaceProgram($input: raceProgramInput!) {
  raceProgram: raceProgramByCondition(input: $input) {
    id
    velodromeCode
    heldDate
    races {
      id
      raceNum
      startTime
      orderDeadline
      entryRacers {
        bicycleNum
        bracketNum
        name
        shortName
        gearRatio
        racingStyle
        charilotoComment
        entryRacerScore {
          averageRaceScore
          winningAverage
          top2Ratio
          top3Ratio
        }
      }
    }
  }
}
"""


def post_graphql(query, variables):
    response = requests.post(
        DMM_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=HEADERS,
        timeout=25,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload.get("data") or {}


def to_iso_date(date_str):
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


def to_jst_hm(value):
    if not value:
        return ""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TOKYO_TZ)
    return dt.strftime("%H:%M")


def float_value(value):
    if value in (None, ""):
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def fetch_programs(date_str):
    data = post_graphql(PROGRAMS_QUERY, {"input": {"heldDate": to_iso_date(date_str)}})
    return data.get("racePrograms") or []


def fetch_program(date_str, venue_cd):
    data = post_graphql(
        PROGRAM_QUERY,
        {"input": {"heldDate": to_iso_date(date_str), "velodromeCode": int(venue_cd)}},
    )
    return data.get("raceProgram")


def scrape_day(date_str):
    programs = fetch_programs(date_str)
    print(f"  DMM {len(programs)}開催")
    day_races = []

    for program in programs:
        venue_cd = f"{int(program['velodromeCode']):02d}"
        venue_name = VENUE_CODES.get(venue_cd, venue_cd)
        detail = fetch_program(date_str, venue_cd)
        if not detail:
            continue

        races = detail.get("races") or []
        print(f"  {venue_name}: {len(races)}レース")
        for race in races:
            entries = []
            for racer in race.get("entryRacers") or []:
                score = racer.get("entryRacerScore") or {}
                umaban = int(racer.get("bicycleNum") or 0)
                entries.append({
                    "waku": int(racer.get("bracketNum") or 0),
                    "umaban": umaban,
                    "name": racer.get("name") or "",
                    "name_kana": "",
                    "score": float_value(score.get("averageRaceScore")),
                    "style": racer.get("racingStyle") or "",
                    "win_rate": float_value(score.get("winningAverage")),
                    "top2_rate": float_value(score.get("top2Ratio")),
                    "top3_rate": float_value(score.get("top3Ratio")),
                    "gear": str(racer.get("gearRatio") or ""),
                    "comment": racer.get("charilotoComment") or "",
                })

            if not entries:
                continue

            race_no = int(race.get("raceNum") or 0)
            day_races.append({
                "race_id": f"{date_str}{venue_cd}{race_no:02d}",
                "venue": venue_name,
                "venue_cd": venue_cd,
                "race_no": race_no,
                "start_time": to_jst_hm(race.get("startTime")),
                "close_time": to_jst_hm(race.get("orderDeadline")),
                "entries": entries,
            })
            names = [entry["name"] for entry in entries]
            print(f"    {race_no}R: {len(entries)}選手 ({', '.join(names[:3])}...)")

    return day_races


def scrape_entries(days_ahead=1):
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now(TOKYO_TZ)
    all_days = {}

    for offset in range(days_ahead + 1):
        target = today + timedelta(days=offset)
        date_str = target.strftime("%Y%m%d")
        print(f"\n[{date_str}] DMM出走表取得中...")
        races = scrape_day(date_str)
        if races:
            all_days[date_str] = races
            out_path = os.path.join(DATA_DIR, f"entries_{date_str}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"date": date_str, "races": races}, f, ensure_ascii=False, separators=(",", ":"))
            print(f"  保存: {len(races)}レース -> {out_path}")

    today_str = today.strftime("%Y%m%d")
    if today_str in all_days:
        with open(os.path.join(DATA_DIR, "today_entries.json"), "w", encoding="utf-8") as f:
            json.dump({"date": today_str, "races": all_days[today_str]}, f, ensure_ascii=False, separators=(",", ":"))

    flat = []
    for date_str in sorted(all_days):
        for race in all_days[date_str]:
            item = dict(race)
            item["date"] = date_str
            flat.append(item)

    upcoming_path = os.path.join(DATA_DIR, "upcoming_entries.json")
    with open(upcoming_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": today_str,
            "updated": datetime.now(TOKYO_TZ).strftime("%Y%m%d%H%M"),
            "days": sorted(all_days),
            "races": flat,
        }, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\nDMM完了: {len(all_days)}日間, {len(flat)}レース")
    return all_days


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    scrape_entries(days)
