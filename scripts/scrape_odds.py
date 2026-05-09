"""オッズ取得スクレイパー — 当日レースの3連単オッズをJSON化"""
import json
import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://keirin.netkeiba.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
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


def get_race_ids(date_str):
    """指定日のレースID一覧を取得"""
    url = f"{BASE_URL}/race/payback_list/?kaisai_date={date_str}"
    r = requests.get(url, headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"}, timeout=15)
    r.encoding = "utf-8"
    return sorted(set(re.findall(r"PaybackRaceId_(\d+)", r.text)))


def parse_odds_table(soup):
    """OddsSelectTableから3連単オッズをパース

    Format: [人気, ?, '6 横田政      2 深井高      5 菊池崇', '7.7']
    → {"6-2-5": 7.7}
    """
    odds = {}
    table = soup.find("table", class_="OddsSelectTable")
    if not table:
        return odds

    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        combo_text = cells[2].text.strip()
        odds_text = cells[3].text.strip()

        # Extract car numbers: "6 横田政      2 深井高      5 菊池崇"
        # Pattern: digit followed by space and kanji name
        numbers = re.findall(r"(\d+)\s+\S", combo_text)
        if len(numbers) >= 3:
            key = f"{numbers[0]}-{numbers[1]}-{numbers[2]}"
            try:
                odds[key] = float(odds_text.replace(",", ""))
            except ValueError:
                pass
        elif len(numbers) == 2:
            key = f"{numbers[0]}-{numbers[1]}"
            try:
                odds[key] = float(odds_text.replace(",", ""))
            except ValueError:
                pass

    return odds


def scrape_odds(date_str=None):
    """指定日の全レースオッズを取得"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"オッズ取得: {date_str}")
    race_ids = get_race_ids(date_str)
    print(f"  {len(race_ids)}レース検出")

    if not race_ids:
        print("  レースなし")
        return

    venues = {}
    for rid in race_ids:
        venue_cd = rid[8:10]
        venue_name = VENUE_CODES.get(venue_cd, venue_cd)
        if venue_name not in venues:
            venues[venue_name] = []
        venues[venue_name].append(rid)

    all_odds = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for venue_name, rids in venues.items():
            print(f"\n  {venue_name}: {len(rids)}レース")

            for rid in rids:
                race_no = int(rid[10:12])
                url = f"{BASE_URL}/race/odds/?race_id={rid}"

                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(3000)
                    html = page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    odds = parse_odds_table(soup)

                    if odds:
                        all_odds.append({
                            "race_id": rid,
                            "venue": venue_name,
                            "race_no": race_no,
                            "trifecta": odds,  # 3連単
                        })
                        print(f"    {race_no}R: {len(odds)}通り (1番人気 {min(odds.values()):.1f}倍)")
                    else:
                        print(f"    {race_no}R: オッズなし")

                    time.sleep(1)
                except Exception as e:
                    print(f"    {race_no}R: ERROR {e}")

        browser.close()

    # 保存
    out_path = os.path.join(DATA_DIR, "today_odds.json")
    result = {
        "date": date_str,
        "updated": datetime.now().strftime("%Y%m%d%H%M"),
        "races": all_odds,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(out_path)
    print(f"\n完了: {len(all_odds)}レース, {size/1024:.1f}KB -> {out_path}")

    return result


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else None
    scrape_odds(date)
