"""結果データを確実に作る。netkeibaが失敗したらDMMへ切り替える。"""
import os
import sys
from datetime import datetime, timedelta

import publish_if_valid
import scrape_results_dmm

TOKYO_TZ = scrape_results_dmm.TOKYO_TZ


def default_result_date():
    now = datetime.now(TOKYO_TZ)
    target = now if now.hour >= 21 else now - timedelta(days=1)
    return target.strftime("%Y%m%d")


def has_results(payload):
    return bool(payload and payload.get("results"))


def run_dmm(date_str):
    payload = scrape_results_dmm.scrape_results(date_str)
    if not has_results(payload):
        raise RuntimeError("DMM results empty")
    publish_if_valid.publish_results()
    return payload


def run_netkeiba(date_str):
    import scrape_results
    import scraper

    scraper.scrape_range(date_str, date_str)
    payload = scrape_results.generate_today_results(date_str)
    if not has_results(payload):
        raise RuntimeError("netkeiba results empty")
    publish_if_valid.publish_results()
    return payload


def ensure_results(date_str=None):
    date_str = date_str or default_result_date()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("GitHub Actions detected. results primary: DMM")
        return run_dmm(date_str)

    try:
        return run_netkeiba(date_str)
    except Exception as exc:
        print(f"netkeiba results failed; fallback to DMM: {exc}")
        return run_dmm(date_str)


if __name__ == "__main__":
    ensure_results(sys.argv[1] if len(sys.argv) > 1 else None)
