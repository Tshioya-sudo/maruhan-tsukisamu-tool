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

from scraper.minrepo import MinRepoScraper
from scraper.sheets import SheetsManager
from analysis.stats import estimate_setting


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


def main():
    start_time = time.time()
    logger.info("=== スクレイピング開始 ===")

    # 1. 初期化
    sheets = SheetsManager()
    scraper = MinRepoScraper(headless=True)

    # 2. 既に取得済みの日付を確認
    existing_dates = sheets.get_existing_dates()
    logger.info(f"取得済み日付数: {len(existing_dates)}")

    # 3. みんレポから日付一覧を取得
    date_list = scraper.scrape_date_list()
    logger.info(f"みんレポ掲載日付数: {len(date_list)}")

    # 4. 未取得の日付だけ処理
    new_dates = [d for d in date_list if d["date"] not in existing_dates]
    logger.info(f"新規取得対象: {len(new_dates)}日分")

    if not new_dates:
        logger.info("新規データなし。終了。")
        return

    # 4.1 1回の実行で処理する日数を制限（GitHub Actions 15分タイムアウト対策）
    # 1日分≒40秒 × 5日 = 約3〜4分。余裕を持って5日に制限。
    # 未取得分が残っていれば次回実行で自動的に続きを取得する。
    MAX_DATES_PER_RUN = 5
    if len(new_dates) > MAX_DATES_PER_RUN:
        logger.info(f"1回の実行上限{MAX_DATES_PER_RUN}日に制限（残り{len(new_dates) - MAX_DATES_PER_RUN}日は次回）")
        new_dates = new_dates[:MAX_DATES_PER_RUN]

    # 4.5 機種名をみんレポの実際の表記と照合
    first_article_id = new_dates[0]["article_id"]
    verified_machines = scraper.get_verified_machine_names(first_article_id)
    logger.info(f"検証済み機種: {verified_machines}")

    # 機種変動チェック
    scraper.check_machine_changes(first_article_id)

    for date_info in new_dates:
        target_date = date_info["date"]
        article_id = date_info["article_id"]
        logger.info(f"--- {target_date} ({date_info['date_text']}) 取得開始 ---")

        try:
            # 5. 全対象機種のデータを取得
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

            # バリデーション
            validate_daily_data(raw_data, target_date)

            # 6. 設定推測を実行
            for row in raw_data:
                result = estimate_setting(
                    row["machine_name"],
                    row.get("total_games"),
                    row.get("bb_count"),
                    row.get("rb_count"),
                )
                row["estimated_setting"] = result["estimated_setting"]
                row["setting_confidence"] = result["confidence"]
                row["estimated_diff"] = calc_diff(row)
                row["day_of_week"] = get_day_of_week(target_date)
                row["unit_suffix"] = (
                    row["unit_number"] % 10 if row["unit_number"] else None
                )

            # 7. Google Sheetsに書き込み
            sheets.append_daily_data(raw_data)

            # 8. サマリー計算・書き込み
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

            # 9. ログ記録
            duration = time.time() - start_time
            sheets.append_log({
                "target_date": target_date,
                "status": "success",
                "units_count": len(raw_data),
                "duration_sec": round(duration, 1),
            })
            logger.info(f"{target_date}: {len(raw_data)}台 取得完了")

        except Exception as e:
            logger.error(f"{target_date}: エラー: {e}", exc_info=True)
            sheets.append_log({
                "target_date": target_date,
                "status": "error",
                "error_message": str(e),
            })

        # みんレポへの負荷配慮
        time.sleep(2)

    total_duration = time.time() - start_time
    logger.info(f"=== スクレイピング完了 ({total_duration:.1f}秒) ===")


if __name__ == "__main__":
    main()
