"""DMM競輪GraphQLからレース結果を取得するフォールバック。"""
import json
import os
import sys
from datetime import datetime, timedelta

import scrape_entries_dmm

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKYO_TZ = scrape_entries_dmm.TOKYO_TZ
VENUE_CODES = scrape_entries_dmm.VENUE_CODES

RESULT_QUERY = """
query GetSingleraceResult($input: raceProgramInput!) {
  raceProgram: raceProgramByCondition(input: $input) {
    id
    velodromeCode
    heldDate
    races {
      id
      raceNum
      isCanceled
      raceEntryStatus
      entryRacers {
        bicycleNum
        bracketNum
        name
        arrivalOrder
        decidingFactor
      }
      singleRaceRefunds {
        betType
        betStatus
        hitNum1
        hitNum2
        hitNum3
        refund
        hitPlaceRank
      }
    }
  }
}
"""

BET_TYPE_MAP = {
    "bracketQuinella": "2枠複",
    "bracketPerfecta": "2枠単",
    "quinella": "2車複",
    "perfecta": "2車単",
    "quinellaPlace": "ワイド",
    "trio": "3連複",
    "trifecta": "3連単",
}


def default_result_date():
    now = datetime.now(TOKYO_TZ)
    target = now if now.hour >= 21 else now - timedelta(days=1)
    return target.strftime("%Y%m%d")


def fetch_program_result(date_str, venue_cd):
    data = scrape_entries_dmm.post_graphql(
        RESULT_QUERY,
        {"input": {"heldDate": scrape_entries_dmm.to_iso_date(date_str), "velodromeCode": int(venue_cd)}},
    )
    return data.get("raceProgram")


def refund_combo(refund):
    numbers = [
        int(refund.get("hitNum1") or 0),
        int(refund.get("hitNum2") or 0),
        int(refund.get("hitNum3") or 0),
    ]
    numbers = [n for n in numbers if n > 0]
    return "-".join(str(n) for n in numbers)


def scrape_results(date_str=None):
    date_str = date_str or default_result_date()
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"[{date_str}] DMM結果取得中...")
    programs = scrape_entries_dmm.fetch_programs(date_str)
    print(f"  DMM {len(programs)}開催")

    results = []
    for program in programs:
        venue_cd = f"{int(program['velodromeCode']):02d}"
        venue_name = VENUE_CODES.get(venue_cd, venue_cd)
        try:
            detail = fetch_program_result(date_str, venue_cd)
        except Exception as exc:
            print(f"  {venue_name}: 取得失敗 {exc}")
            continue
        if not detail:
            continue

        venue_results = 0
        for race in detail.get("races") or []:
            race_no = int(race.get("raceNum") or 0)
            finishers = []
            for racer in race.get("entryRacers") or []:
                rank = int(racer.get("arrivalOrder") or 0)
                if rank <= 0:
                    continue
                finishers.append({
                    "rank": rank,
                    "waku": int(racer.get("bracketNum") or 0),
                    "umaban": int(racer.get("bicycleNum") or 0),
                    "name": racer.get("name") or "",
                    "kimarite": racer.get("decidingFactor") or "",
                })

            finishers.sort(key=lambda item: item["rank"])
            if len(finishers) < 3:
                continue

            paybacks = []
            for refund in race.get("singleRaceRefunds") or []:
                if refund.get("betStatus") != "decision":
                    continue
                payout = int(refund.get("refund") or 0)
                combo = refund_combo(refund)
                bet_type = BET_TYPE_MAP.get(refund.get("betType") or "")
                if not bet_type or not combo or payout <= 0:
                    continue
                paybacks.append({
                    "type": bet_type,
                    "combination": combo,
                    "payout": payout,
                })

            results.append({
                "race_id": f"{date_str}{venue_cd}{race_no:02d}",
                "venue": venue_name,
                "race_no": race_no,
                "finishers": finishers[:5],
                "paybacks": paybacks[:8],
            })
            venue_results += 1

        print(f"  {venue_name}: {venue_results}レース")

    payload = {"date": date_str, "results": sorted(results, key=lambda r: r["race_id"])}
    out_path = os.path.join(DATA_DIR, "today_results.json")
    dated_path = os.path.join(DATA_DIR, f"results_{date_str}.json")
    for path in [out_path, dated_path]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"DMM結果完了: {len(results)}レース -> {out_path}")
    return payload


if __name__ == "__main__":
    scrape_results(sys.argv[1] if len(sys.argv) > 1 else None)
