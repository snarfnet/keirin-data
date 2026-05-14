"""今日のレース結果をJSON化 → today_results.json"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKYO_TZ = ZoneInfo("Asia/Tokyo")


def generate_today_results(date_str=None):
    if date_str is None:
        date_str = datetime.now(TOKYO_TZ).strftime("%Y%m%d")

    results_path = os.path.join(DATA_DIR, "race_results.csv")
    paybacks_path = os.path.join(DATA_DIR, "paybacks.csv")

    def write_empty_results():
        os.makedirs(DATA_DIR, exist_ok=True)
        out = {"date": date_str, "results": []}
        out_path = os.path.join(DATA_DIR, "today_results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        print(f"No results source for {date_str}; wrote empty results -> {out_path}")
        return out

    if not os.path.exists(results_path):
        print("race_results.csv not found")
        return write_empty_results()

    df = pd.read_csv(results_path, encoding="utf-8-sig", dtype=str)
    df = df[df["date"] == date_str]

    if df.empty:
        print(f"No results for {date_str}")
        # Create empty file
        return write_empty_results()

    # Load paybacks
    pb_df = pd.read_csv(paybacks_path, encoding="utf-8-sig", dtype=str)
    pb_df = pb_df[pb_df["date"] == date_str]

    # Group by race_id (exclude sub-races _02 etc for simplicity)
    main_races = df[~df["race_id"].str.contains("_")]

    race_ids = main_races["race_id"].unique()
    results = []

    for rid in sorted(race_ids):
        race_df = main_races[main_races["race_id"] == rid].copy()
        race_df["rank"] = pd.to_numeric(race_df["rank"], errors="coerce")
        race_df = race_df.sort_values("rank")

        venue = race_df.iloc[0]["venue"]
        race_no = int(race_df.iloc[0]["race_no"])

        finishers = []
        for _, row in race_df.iterrows():
            rank = int(row["rank"]) if pd.notna(row["rank"]) else 99
            finishers.append({
                "rank": rank,
                "waku": int(row["waku"]) if pd.notna(row.get("waku")) else 0,
                "umaban": int(row["umaban"]) if pd.notna(row.get("umaban")) else 0,
                "name": str(row["name"]),
                "kimarite": str(row.get("kimarite", "")) if pd.notna(row.get("kimarite")) else "",
            })

        # Paybacks for this race
        race_pb = pb_df[pb_df["race_id"] == rid]
        paybacks = []
        bet_type_map = {"2車単": "2車単", "2車複": "2車複", "3連単": "3連単", "3連複": "3連複", "ワイド": "ワイド"}

        for _, pb_row in race_pb.iterrows():
            bt = str(pb_row.get("bet_type", ""))
            combo = str(pb_row.get("combination", ""))
            payout = pb_row.get("payout", "0")
            try:
                payout_int = int(float(payout))
            except (ValueError, TypeError):
                payout_int = 0

            if bt and combo and payout_int > 0:
                paybacks.append({
                    "type": bt,
                    "combination": combo,
                    "payout": payout_int,
                })

        results.append({
            "race_id": rid,
            "venue": venue,
            "race_no": race_no,
            "finishers": finishers[:5],
            "paybacks": paybacks[:5],
        })

    out = {"date": date_str, "results": results}
    out_path = os.path.join(DATA_DIR, "today_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(out_path)
    print(f"完了: {len(results)}レース, {size/1024:.1f}KB -> {out_path}")
    return out


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else None
    generate_today_results(date)
