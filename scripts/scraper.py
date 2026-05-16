"""
競輪レース結果スクレイパー
keirin.netkeiba.com から過去レース結果を取得してCSV保存
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import json
import sys
from datetime import datetime, timedelta

BASE_URL = "https://keirin.netkeiba.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 場コード→場名
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
    "71": "高松", "72": "小松島", "73": "高知", "74": "松山",
    "81": "小倉", "83": "久留米", "84": "武雄", "85": "佐世保",
    "86": "別府", "87": "熊本",
}


def get_race_ids_for_date(date_str):
    """指定日のレースID一覧を取得 (date_str: YYYYMMDD)"""
    url = f"{BASE_URL}/race/payback_list/?kaisai_date={date_str}"
    headers = {**HEADERS, "Referer": url}
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "utf-8"

    import re
    ids = re.findall(r"PaybackRaceId_(\d+)", r.text)
    return sorted(set(ids))


def parse_race_result(race_id):
    """個別レース結果をパース"""
    url = f"{BASE_URL}/race/payback_list/api_payback_result_v2.html?race_id={race_id}"
    headers = {**HEADERS, "Referer": f"{BASE_URL}/race/payback_list/"}
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "utf-8"
    soup = BeautifulSoup(r.text, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        return None, None

    # race_id: YYYYMMDD + JYO(2) + RACE(2)
    date_str = race_id[:8]
    venue_cd = race_id[8:10]
    race_no = int(race_id[10:12])
    venue_name = VENUE_CODES.get(venue_cd, venue_cd)

    results = []
    paybacks = []
    sub_race = 0  # サブレース番号

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        table_classes = table.get("class", [])
        is_result = "ResultRefund" in table_classes
        is_payout = "Payout_Detail_Table" in table_classes

        if is_result:
            sub_race += 1
            sub_id = f"{race_id}_{sub_race:02d}" if sub_race > 1 else race_id
            for row in rows[1:]:
                cells = [td.text.strip().replace("\n", " ") for td in row.find_all("td")]
                if len(cells) >= 6:
                    results.append({
                        "race_id": sub_id,
                        "date": date_str,
                        "venue": venue_name,
                        "venue_cd": venue_cd,
                        "race_no": race_no,
                        "sub_race": sub_race,
                        "rank": cells[0].replace("着", ""),
                        "waku": cells[1],
                        "umaban": cells[2],
                        "name": cells[3],
                        "margin": cells[4],
                        "agari": cells[5],
                        "kimarite": cells[6] if len(cells) > 6 else "",
                        "sb": cells[7] if len(cells) > 7 else "",
                    })
        elif is_payout:
            sub_id = f"{race_id}_{sub_race:02d}" if sub_race > 1 else race_id
            for row in rows:
                cells = [td.text.strip().replace("\n", " ") for td in row.find_all("td")]
                if len(cells) >= 3 and "円" in cells[-2]:
                    bet_type = cells[0] if len(cells) == 4 else ""
                    combo = cells[-3] if len(cells) >= 4 else cells[0]
                    payout_str = cells[-2]
                    pop = cells[-1] if cells[-1] and "人気" in cells[-1] else ""
                    if not bet_type and len(cells) == 3:
                        combo = cells[0]
                        payout_str = cells[1]
                        pop = cells[2]
                    paybacks.append({
                        "race_id": sub_id,
                        "date": date_str,
                        "venue": venue_name,
                        "race_no": race_no,
                        "sub_race": sub_race,
                        "bet_type": bet_type,
                        "combination": combo,
                        "payout": payout_str.replace(",", "").replace("円", ""),
                        "popularity": pop.replace("人気", ""),
                    })

    return results, paybacks


def scrape_date(date_str):
    """1日分のレース結果を取得"""
    print(f"[{date_str}] レースID取得中...")
    race_ids = get_race_ids_for_date(date_str)
    if not race_ids:
        print(f"  レースなし")
        return [], []

    print(f"  {len(race_ids)}レース検出")
    all_results = []
    all_paybacks = []

    for race_id in race_ids:
        try:
            results, paybacks = parse_race_result(race_id)
            if results:
                all_results.extend(results)
            if paybacks:
                all_paybacks.extend(paybacks)
            time.sleep(1.5)  # サーバー負荷軽減
        except Exception as e:
            print(f"  ERROR {race_id}: {e}")

    print(f"  取得完了: {len(all_results)}着順, {len(all_paybacks)}払戻")
    return all_results, all_paybacks


def scrape_range(start_date, end_date):
    """日付範囲のレース結果を取得してCSV保存"""
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")

    all_results = []
    all_paybacks = []
    current = start

    while current <= end:
        date_str = current.strftime("%Y%m%d")
        results, paybacks = scrape_date(date_str)
        all_results.extend(results)
        all_paybacks.extend(paybacks)

        # 日ごとに中間保存
        if all_results:
            pd.DataFrame(all_results).to_csv(
                os.path.join(DATA_DIR, "race_results.csv"), index=False, encoding="utf-8-sig"
            )
        if all_paybacks:
            pd.DataFrame(all_paybacks).to_csv(
                os.path.join(DATA_DIR, "paybacks.csv"), index=False, encoding="utf-8-sig"
            )

        current += timedelta(days=1)
        time.sleep(2)  # 日付間のクールダウン

    print(f"\n=== 完了 ===")
    print(f"期間: {start_date} - {end_date}")
    print(f"着順データ: {len(all_results)}件")
    print(f"払戻データ: {len(all_paybacks)}件")
    return all_results, all_paybacks


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        start_date = sys.argv[1]
        end_date = sys.argv[2] if len(sys.argv) >= 3 else start_date
        scrape_range(start_date, end_date)
    else:
        # 直近1週間のデータを取得（テスト）
        end = datetime.now()
        start = end - timedelta(days=7)
        scrape_range(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
