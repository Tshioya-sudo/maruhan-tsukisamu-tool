"""
過去データの設定推測を再計算 + 店舗名一括付与スクリプト。

機能:
1. AT機の出率（payout_rate）を使った設定推定ロジックで J列・K列・L列を再計算
2. P列（store_name）が空の行に「マルハン月寒店」を一括付与

変更対象列:
  J列 (10): estimated_setting
  K列 (11): setting_confidence
  L列 (12): estimated_diff
  P列 (16): store_name（空の場合のみ）
"""
import sys
import os
import logging
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
_site_packages = Path(PROJECT_ROOT).parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

from scraper.sheets import SheetsManager
from analysis.stats import estimate_setting


def safe_int(val) -> int | None:
    try:
        return int(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None


def safe_float(val) -> float | None:
    try:
        return float(val) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None


def calc_diff(row: dict) -> int | None:
    """推定差枚（ジャグラー系用: BB*312 + RB*104 - G*3）"""
    games = safe_int(row.get("total_games"))
    bb = safe_int(row.get("bb_count")) or 0
    rb = safe_int(row.get("rb_count")) or 0
    if not games:
        return None
    payout = bb * 312 + rb * 104
    invest = games * 3
    return payout - invest


def main():
    sheets = SheetsManager()
    ws = sheets.spreadsheet.worksheet(sheets.SHEET_DAILY_DATA)

    logger.info("daily_dataを読み込み中...")
    records = ws.get_all_records()
    logger.info(f"{len(records)}行を読み込みました")

    updates = []
    updated = 0
    skipped = 0

    for i, row in enumerate(records):
        row_num = i + 2  # 1行目はヘッダーなので2行目から

        machine_name = row.get("machine_name", "")
        total_games = safe_int(row.get("total_games"))
        bb_count = safe_int(row.get("bb_count"))
        rb_count = safe_int(row.get("rb_count"))
        payout_rate = safe_float(row.get("payout_rate"))

        # 設定推測を再計算
        result = estimate_setting(
            machine_name, total_games, bb_count, rb_count,
            payout_rate=payout_rate,
        )
        new_setting = result["estimated_setting"]
        new_confidence = result["confidence"]

        # estimated_diff: 既存値があればそのまま使用、なければ計算
        existing_diff = safe_int(row.get("estimated_diff"))
        if existing_diff is not None:
            new_diff = existing_diff
        else:
            new_diff = calc_diff(row)

        # 既存値と比較（変更がある行のみ更新対象に追加）
        old_setting = safe_int(row.get("estimated_setting"))
        old_confidence = safe_float(row.get("setting_confidence"))

        if new_setting != old_setting or abs((new_confidence or 0) - (old_confidence or 0)) > 0.001:
            updates.append({
                "range": f"J{row_num}:L{row_num}",
                "values": [[
                    new_setting if new_setting is not None else "",
                    new_confidence,
                    new_diff if new_diff is not None else "",
                ]],
            })
            updated += 1
        else:
            skipped += 1

    logger.info(f"更新対象: {updated}行, スキップ: {skipped}行")

    if updates:
        logger.info("J〜L列（設定推測・信頼度・差枚）を一括更新中...")
        ws.batch_update(updates, value_input_option="USER_ENTERED")
        logger.info(f"完了: {updated}行を更新しました")
    else:
        logger.info("更新対象なし。全行が最新状態です")

    # --- P列（store_name）の一括付与 ---
    logger.info("P列（店舗名）の空欄チェック中...")
    store_updates = []
    for i, row in enumerate(records):
        row_num = i + 2
        existing_store = str(row.get("store_name", row.get("店舗名", ""))).strip()
        if not existing_store:
            store_updates.append({
                "range": f"P{row_num}",
                "values": [["マルハン月寒店"]],
            })

    if store_updates:
        logger.info(f"P列に店舗名を付与: {len(store_updates)}行...")
        ws.batch_update(store_updates, value_input_option="USER_ENTERED")
        logger.info(f"完了: {len(store_updates)}行に「マルハン月寒店」を付与しました")
    else:
        logger.info("P列: 全行に店舗名が設定済みです")


if __name__ == "__main__":
    main()
