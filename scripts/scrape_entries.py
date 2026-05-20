"""出走表を取得してJSONに変換（今日〜7日先まで）"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://keirin.netkeiba.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TOKYO_TZ = ZoneInfo("Asia/Tokyo")
LIST_RETRIES = 3
DETAIL_RETRIES = 2
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
    last_error = None
    for attempt in range(1, LIST_RETRIES + 1):
        try:
            r = requests.get(url, headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"}, timeout=15)
            r.raise_for_status()
            r.encoding = "utf-8"
            race_ids = sorted(set(re.findall(r"PaybackRaceId_(\d+)", r.text)))
            if race_ids or attempt == LIST_RETRIES:
                return race_ids
        except requests.RequestException as exc:
            last_error = exc
        if attempt < LIST_RETRIES:
            time.sleep(2 * attempt)
    if last_error:
        print(f"  レースID取得失敗: {last_error}")
    return []


def guess_race_ids(date_str):
    """一覧が403の時用。全場コード×12Rを直接確認する。"""
    return [
        f"{date_str}{venue_cd}{race_no:02d}"
        for venue_cd in sorted(VENUE_CODES.keys())
        for race_no in range(1, 13)
    ]


def parse_entry_table(soup, race_id):
    """出走表テーブルをパース"""
    tables = soup.find_all("table", class_="RaceCard_Table")
    if not tables:
        return []

    table = tables[1] if len(tables) > 1 else tables[0]
    entries = []

    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 15:
            continue

        waku = cells[0].text.strip()
        umaban = cells[1].text.strip()
        name_cell = cells[4].text.strip()

        lines = [l.strip() for l in name_cell.split() if l.strip()]
        name_kana = lines[0] if lines else ""
        name_kanji = lines[1] if len(lines) > 1 else ""
        name_kanji = name_kanji.replace("お気に入り選手", "").strip()

        score = cells[5].text.strip()
        style = cells[6].text.strip()
        style_clean = re.sub(r"\d+", "", style)

        win_rate = cells[17].text.strip().replace("%", "") if len(cells) > 17 else ""
        top2_rate = cells[18].text.strip().replace("%", "") if len(cells) > 18 else ""
        top3_rate = cells[19].text.strip().replace("%", "") if len(cells) > 19 else ""
        gear = cells[20].text.strip() if len(cells) > 20 else ""
        comment = cells[21].text.strip() if len(cells) > 21 else ""

        entries.append({
            "waku": int(waku) if waku.isdigit() else 0,
            "umaban": int(umaban) if umaban.isdigit() else 0,
            "name": name_kanji,
            "name_kana": name_kana,
            "score": float(score) if score else 0,
            "style": style_clean,
            "win_rate": float(win_rate) if win_rate else 0,
            "top2_rate": float(top2_rate) if top2_rate else 0,
            "top3_rate": float(top3_rate) if top3_rate else 0,
            "gear": gear,
            "comment": comment,
        })

    return entries


def parse_race_meta(soup):
    """発走時刻などのレース基本情報を取得"""
    data = soup.find("div", class_="Race_Data")
    text = data.get_text(" ", strip=True) if data else soup.get_text(" ", strip=True)
    times = re.findall(r"\d{1,2}:\d{2}", text)
    return {
        "start_time": times[0] if times else "",
        "close_time": times[1] if len(times) > 1 else "",
    }


def fetch_entry_html(race_id):
    url = f"{BASE_URL}/race/entry/?race_id={race_id}"
    last_error = None
    for attempt in range(1, DETAIL_RETRIES + 1):
        try:
            r = requests.get(url, headers={**HEADERS, "Referer": url}, timeout=20)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < DETAIL_RETRIES:
                time.sleep(2)
    raise RuntimeError(f"entry fetch failed: {last_error}")


def scrape_day(date_str, browser_page=None):
    """1日分の出走表を取得（ブラウザページ再利用）"""
    race_ids = get_race_ids(date_str)
    today_str = datetime.now(TOKYO_TZ).strftime("%Y%m%d")
    using_guessed_ids = False
    if not race_ids:
        if date_str > today_str:
            print("  future race list not available yet; skip guessed deep scan")
            return []
        using_guessed_ids = True
        race_ids = guess_race_ids(date_str)
        print(f"  一覧なし。直接確認に切替: {len(race_ids)}候補")

    venues = {}
    for rid in race_ids:
        venue_cd = rid[8:10]
        venue_name = VENUE_CODES.get(venue_cd, venue_cd)
        if venue_name not in venues:
            venues[venue_name] = []
        venues[venue_name].append(rid)

    day_races = []
    for venue_name, rids in venues.items():
        print(f"  {venue_name}: {len(rids)}レース")
        for rid in rids:
            race_no = int(rid[10:12])
            url = f"{BASE_URL}/race/entry/?race_id={rid}"
            try:
                html = fetch_entry_html(rid)
                soup = BeautifulSoup(html, "html.parser")
                entries = parse_entry_table(soup, rid)
                if not entries and browser_page is not None:
                    browser_page.goto(url, timeout=30000)
                    browser_page.wait_for_timeout(3000)
                    html = browser_page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    entries = parse_entry_table(soup, rid)

                if entries:
                    meta = parse_race_meta(soup)
                    day_races.append({
                        "race_id": rid,
                        "venue": venue_name,
                        "venue_cd": rid[8:10],
                        "race_no": race_no,
                        **meta,
                        "entries": entries,
                    })
                    names = [e["name"] for e in entries]
                    print(f"    {race_no}R: {len(entries)}選手 ({', '.join(names[:3])}...)")
                elif date_str > today_str and not using_guessed_ids:
                    day_races.append({
                        "race_id": rid,
                        "venue": venue_name,
                        "venue_cd": rid[8:10],
                        "race_no": race_no,
                        "entries": [],
                    })
                    print(f"    {race_no}R: レース予定のみ")
                else:
                    print(f"    {race_no}R: 出走表なし")
                time.sleep(0.25)
            except Exception as e:
                print(f"    {race_no}R: ERROR {e}")

    return day_races


def scrape_entries(days_ahead=7):
    """今日から指定日数先までの出走表を取得"""
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now(TOKYO_TZ)
    all_days = {}

    fallback_browser = None
    fallback_page = None
    try:
        for offset in range(days_ahead + 1):
            target = today + timedelta(days=offset)
            date_str = target.strftime("%Y%m%d")
            print(f"\n[{date_str}] 出走表取得中...")

            race_ids = get_race_ids(date_str)
            print(f"  {len(race_ids)}レース検出")

            if not race_ids:
                print("  一覧取得なし。直接確認で継続")

            races = scrape_day(date_str, fallback_page)
            needs_fallback = not races or all(not race["entries"] for race in races)
            if needs_fallback:
                with sync_playwright() as p:
                    fallback_browser = p.chromium.launch(headless=True)
                    fallback_page = fallback_browser.new_page()
                    races = scrape_day(date_str, fallback_page)

            if races:
                all_days[date_str] = races
                # 日別ファイル保存
                out = {"date": date_str, "races": races}
                out_path = os.path.join(DATA_DIR, f"entries_{date_str}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
                print(f"  保存: {len(races)}レース -> {out_path}")
    finally:
        if fallback_browser is not None:
            fallback_browser.close()

    # today_entries.json は当日分
    today_str = today.strftime("%Y%m%d")
    if today_str in all_days:
        out_path = os.path.join(DATA_DIR, "today_entries.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"date": today_str, "races": all_days[today_str]},
                      f, ensure_ascii=False, separators=(",", ":"))

    # upcoming_entries.json は全日分まとめ
    all_races_flat = []
    for date_str in sorted(all_days.keys()):
        for race in all_days[date_str]:
            race["date"] = date_str
            all_races_flat.append(race)

    upcoming_path = os.path.join(DATA_DIR, "upcoming_entries.json")
    with open(upcoming_path, "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.now(TOKYO_TZ).strftime("%Y%m%d%H%M"),
            "days": sorted(all_days.keys()),
            "races": all_races_flat,
        }, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(upcoming_path)
    print(f"\n完了: {len(all_days)}日間, {len(all_races_flat)}レース, {size/1024:.1f}KB")

    return all_days


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    scrape_entries(days)
