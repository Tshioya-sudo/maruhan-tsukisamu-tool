"""
Google Sheets 初期セットアップスクリプト。
スプレッドシートに4つのシートを作成し、ヘッダー行を自動入力する。

使い方:
  set SPREADSHEET_ID=あなたのスプレッドシートID
  python scripts/setup_sheets.py
"""
import sys
import os
from pathlib import Path

# 日本語パス環境でのsite-packages解決
_project_root = Path(__file__).resolve().parent.parent
_site_packages = _project_root.parent / "Lib" / "site-packages"
if _site_packages.exists():
    sys.path.insert(0, str(_site_packages))
sys.path.insert(0, str(_project_root))

from scraper.sheets import SheetsManager

# 各シートのヘッダー定義
SHEET_HEADERS = {
    "daily_data": [
        "日付", "機種名", "台番号", "総G数",
        "BB回数", "RB回数", "合算確率", "BB率", "RB率",
        "推定設定", "信頼度", "推定差枚",
        "曜日", "台番末尾",
    ],
    "daily_summary": [
        "日付", "平均G数", "取得台数", "高設定台数",
        "好調機種", "好調末尾", "曜日",
    ],
    "scrape_log": [
        "実行日時", "対象日", "ステータス",
        "取得台数", "エラー内容", "処理時間(秒)",
    ],
    "machines": [
        "機種名", "タイプ", "メーカー",
        "設定1機械割", "設定6機械割",
        "設定1REG確率", "設定6REG確率",
    ],
}


def main():
    print("=== Google Sheets 初期セットアップ ===")
    sheets = SheetsManager()
    spreadsheet = sheets.spreadsheet

    existing_sheets = [ws.title for ws in spreadsheet.worksheets()]
    print(f"既存シート: {existing_sheets}")

    for sheet_name, headers in SHEET_HEADERS.items():
        if sheet_name in existing_sheets:
            ws = spreadsheet.worksheet(sheet_name)
            # ヘッダーが空なら設定
            first_row = ws.row_values(1)
            if not first_row:
                ws.append_rows([headers], value_input_option="RAW")
                print(f"  [{sheet_name}] ヘッダー設定完了")
            else:
                print(f"  [{sheet_name}] 既にヘッダーあり。スキップ")
        else:
            ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
            ws.append_rows([headers], value_input_option="RAW")
            print(f"  [{sheet_name}] シート作成 + ヘッダー設定完了")

    # デフォルトの「シート1」(Sheet1)が残っていたら削除
    for ws in spreadsheet.worksheets():
        if ws.title in ("Sheet1", "シート1") and len(spreadsheet.worksheets()) > 1:
            try:
                spreadsheet.del_worksheet(ws)
                print(f"  [{ws.title}] デフォルトシート削除")
            except Exception:
                pass

    # machinesシートに機種マスタデータを投入
    import json

    machines_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "machines.json"
    )
    with open(machines_path, "r", encoding="utf-8") as f:
        machines_data = json.load(f)["machines"]

    ws_machines = spreadsheet.worksheet("machines")
    existing_data = ws_machines.get_all_values()
    if len(existing_data) <= 1:  # ヘッダーのみ
        rows = []
        for m in machines_data:
            settings = m.get("settings", {})
            s1 = settings.get("1", {})
            s6 = settings.get("6", {})
            rows.append([
                m["machine_name"],
                m.get("machine_type", ""),
                m.get("maker", ""),
                s1.get("payout", ""),
                s6.get("payout", ""),
                s1.get("reg", ""),
                s6.get("reg", ""),
            ])
        if rows:
            ws_machines.append_rows(rows, value_input_option="USER_ENTERED")
            print(f"  [machines] {len(rows)}機種のマスタデータ投入完了")
    else:
        print("  [machines] 既にデータあり。スキップ")

    print("=== セットアップ完了 ===")


if __name__ == "__main__":
    main()
