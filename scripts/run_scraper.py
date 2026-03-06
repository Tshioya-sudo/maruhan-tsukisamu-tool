"""
メイン実行スクリプト。
GitHub Actions または手動で実行される。

処理フロー:
1. Google Sheetsから既に取得済みの日付一覧を取得
2. みんレポの店舗ページから日付一覧を取得
3. 未取得の日付について、各日付ページからデータ取得
4. 設定推測を実行
5. Google Sheetsに書き込み
6. ログを記録
"""
import sys
import os
import time
import logging
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
# ローカル環境の日本語パス対応: site-packagesを明示追加
_site_packages = Path(PROJECT_ROOT).parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, PROJECT_ROOT)

# ログディレクトリ作成
log_dir = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(log_dir, exist_ok=True)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(log_dir, "scraper.log"), encoding="utf-8"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

import json

from scraper.minrepo import MinRepoScraper
from scraper.sheets import SheetsManager
from analysis.stats import estimate_setting


def load_stores_config():
    """config/stores.json から店舗定義を読み込む"""
    config_path = os.path.join(PROJECT_ROOT, "config", "stores.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)["stores"]


def validate_daily_data(raw_data: list[dict], target_date: str) -> bool:
    """取得データの妥当性チェック"""
    if len(raw_data) == 0:
        logger.error(f"[ALERT] {target_date}: データ0件。HTML構造変更の可能性")
        return False
    if len(raw_data) < 50:
        # Phase 1対象は140台前後。50台未満は異常
        logger.warning(
            f"[WARN] {target_date}: データ{len(raw_data)}件。一部機種の取得失敗の可能性"
        )
    for row in raw_data:
        # 台番号が3桁の正の整数であること
        un = row.get("unit_number")
        if not un or un < 100 or un > 999:
            logger.warning(f"[WARN] 異常な台番号: {un}")
        # G数が0以上の整数であること
        tg = row.get("total_games")
        if tg is not None and tg < 0:
            logger.warning(f"[WARN] 異常なG数: {tg}")
    return True


def calc_diff(row: dict) -> int | None:
    """推定差枚（簡易版: G数とボーナス回数から概算）"""
    games = row.get("total_games")
    bb = row.get("bb_count") or 0
    rb = row.get("rb_count") or 0
    if not games:
        return None
    # ジャグラー系: BIG≒312枚, REG≒104枚
    payout = bb * 312 + rb * 104
    invest = games * 3  # 3枚掛け
    return payout - invest


def get_day_of_week(date_str: str) -> int | None:
    """'2026-02-16' → 6 (日曜)"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").weekday()
    except Exception:
        return None


def scrape_store(sheets: SheetsManager, store: dict):
    """1店舗分のスクレイピングを実行"""
    store_name = store["store_name"]
    store_path = store["store_path"]
    logger.info(f"=== {store_name} スクレイピング開始 ===")

    scraper = MinRepoScraper(store_path=store_path, headless=True)

    # 店舗別に取得済み日付を確認
    existing_dates = sheets.get_existing_dates(store_name=store_name)
    logger.info(f"[{store_name}] 取得済み日付数: {len(existing_dates)}")

    date_list = scraper.scrape_date_list()
    logger.info(f"[{store_name}] みんレポ掲載日付数: {len(date_list)}")

    new_dates = [d for d in date_list if d["date"] not in existing_dates]
    new_dates.sort(key=lambda d: d["date"], reverse=True)
    logger.info(f"[{store_name}] 新規取得対象: {len(new_dates)}日分")

    if not new_dates:
        logger.info(f"[{store_name}] 新規データなし。")
        return 0

    MAX_DATES_PER_RUN = 2
    if len(new_dates) > MAX_DATES_PER_RUN:
        logger.info(f"[{store_name}] 1回の実行上限{MAX_DATES_PER_RUN}日に制限（残り{len(new_dates) - MAX_DATES_PER_RUN}日は次回）")
        new_dates = new_dates[:MAX_DATES_PER_RUN]

    first_article_id = new_dates[0]["article_id"]
    verified_machines = scraper.get_verified_machine_names(first_article_id)
    logger.info(f"[{store_name}] 検証済み機種: {verified_machines}")

    total_units = 0
    for date_info in new_dates:
        target_date = date_info["date"]
        article_id = date_info["article_id"]
        logger.info(f"--- [{store_name}] {target_date} ({date_info['date_text']}) 取得開始 ---")

        try:
            raw_data = scraper.scrape_daily_all_machines(
                article_id, target_date, machines=verified_machines
            )

            if not raw_data:
                sheets.append_log({
                    "target_date": target_date,
                    "status": "no_data",
                    "units_count": 0,
                })
                continue

            validate_daily_data(raw_data, target_date)

            before = len(raw_data)
            raw_data = [
                r for r in raw_data
                if r.get("unit_number") and 100 <= r["unit_number"] <= 9999
            ]
            if len(raw_data) < before:
                logger.warning(
                    f"[{store_name}] {target_date}: 異常台番号 {before - len(raw_data)}行を除外"
                )

            for row in raw_data:
                result = estimate_setting(
                    row["machine_name"],
                    row.get("total_games"),
                    row.get("bb_count"),
                    row.get("rb_count"),
                    payout_rate=row.get("payout_rate"),
                )
                row["estimated_setting"] = result["estimated_setting"]
                row["setting_confidence"] = result["confidence"]
                if row.get("diff_medals") is not None:
                    row["estimated_diff"] = row["diff_medals"]
                else:
                    row["estimated_diff"] = calc_diff(row)
                row["day_of_week"] = get_day_of_week(target_date)
                row["unit_suffix"] = (
                    row["unit_number"] % 10 if row["unit_number"] else None
                )
                # 店舗名を付与
                row["store_name"] = store_name

            sheets.append_daily_data(raw_data)

            high_count = sum(
                1 for r in raw_data
                if r.get("estimated_setting") and r["estimated_setting"] >= 4
            )
            sheets.append_summary({
                "play_date": target_date,
                "avg_games": date_info.get("avg_games"),
                "total_units": len(raw_data),
                "high_setting_count": high_count,
                "day_of_week": get_day_of_week(target_date),
            })

            sheets.append_log({
                "target_date": target_date,
                "status": "success",
                "units_count": len(raw_data),
            })
            total_units += len(raw_data)
            logger.info(f"[{store_name}] {target_date}: {len(raw_data)}台 取得完了")

        except Exception as e:
            logger.error(f"[{store_name}] {target_date}: エラー: {e}", exc_info=True)
            sheets.append_log({
                "target_date": target_date,
                "status": "error",
                "error_message": str(e),
            })

        time.sleep(2)

    return total_units


def main():
    start_time = time.time()
    logger.info("=== スクレイピング開始 ===")

    sheets = SheetsManager()
    stores = load_stores_config()
    logger.info(f"対象店舗数: {len(stores)}")

    total_units = 0
    for store in stores:
        total_units += scrape_store(sheets, store)

    # データを日付順にソート
    sheets.sort_daily_data_by_date()

    total_duration = time.time() - start_time
    logger.info(f"=== スクレイピング完了: 合計{total_units}台 ({total_duration:.1f}秒) ===")


if __name__ == "__main__":
    main()
