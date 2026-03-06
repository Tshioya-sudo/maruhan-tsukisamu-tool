"""
Google Sheets 読み書きクラス。
GitHub Actions環境ではSecretsから、ローカルではcredentials.jsonから認証する。
"""
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SheetsManager:
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    # シート名定数
    SHEET_DAILY_DATA = "daily_data"
    SHEET_DAILY_SUMMARY = "daily_summary"
    SHEET_SCRAPE_LOG = "scrape_log"
    SHEET_MACHINES = "machines"

    def __init__(self):
        """GitHub Secrets / Streamlit Cloud / ローカルファイルから認証"""
        creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")

        if creds_json:
            # GitHub Actions環境（環境変数）
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=self.SCOPES
            )
        else:
            # Streamlit Cloud または ローカルを判定
            try:
                import streamlit as st
                secrets = st.secrets
                if "GOOGLE_SHEETS_CREDENTIALS" in secrets:
                    creds_dict = json.loads(secrets["GOOGLE_SHEETS_CREDENTIALS"])
                    creds = Credentials.from_service_account_info(
                        creds_dict, scopes=self.SCOPES
                    )
                    if not spreadsheet_id:
                        spreadsheet_id = secrets.get("SPREADSHEET_ID", "")
                else:
                    raise KeyError("not in secrets")
            except Exception:
                # ローカル開発環境（credentials.jsonファイル）
                creds_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "config",
                    "credentials.json",
                )
                creds = Credentials.from_service_account_file(creds_path, scopes=self.SCOPES)

        self.client = gspread.authorize(creds)
        self.spreadsheet_id = spreadsheet_id
        self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        logger.info("Google Sheets接続成功")

    def get_existing_dates(self, store_name: str = None) -> set[str]:
        """既に取得済みの日付一覧を返す（store_name指定時は店舗別にフィルタ）"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_DATA)
        dates = ws.col_values(1)[1:]  # ヘッダー除く
        if store_name:
            # P列(16列目)のstore_nameでフィルタ
            stores = ws.col_values(16)[1:]
            # 列長が足りない場合は空文字で埋める
            stores.extend([""] * (len(dates) - len(stores)))
            return set(
                d for d, s in zip(dates, stores)
                if d.strip() and s.strip() == store_name
            )
        # 空行を除外
        return set(d for d in dates if d.strip())

    def append_daily_data(self, rows: list[dict]):
        """daily_dataシートにデータを追加（append_rows で一括書き込み）"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_DATA)
        values = []
        for r in rows:
            values.append([
                r["play_date"],
                r["machine_name"],
                r["unit_number"],
                r.get("total_games"),
                r.get("bb_count"),
                r.get("rb_count"),
                r.get("combined_prob"),
                r.get("bb_prob"),
                r.get("rb_prob"),
                r.get("estimated_setting"),
                r.get("setting_confidence"),
                r.get("estimated_diff"),
                r.get("day_of_week"),
                r.get("unit_suffix"),
                r.get("payout_rate"),
                r.get("store_name"),
            ])
        if values:
            # append_rows（複数形）を使用。append_row（単数形）は1行ずつAPIコールになるため禁止。
            ws.append_rows(values, value_input_option="USER_ENTERED")
            logger.info(f"daily_data: {len(values)}行書き込み完了")

    def append_summary(self, summary: dict):
        """daily_summaryシートにサマリーを追加"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_SUMMARY)
        row = [
            summary["play_date"],
            summary.get("avg_games"),
            summary.get("total_units"),
            summary.get("high_setting_count"),
            summary.get("featured_machines", ""),
            summary.get("featured_suffixes", ""),
            summary.get("day_of_week"),
        ]
        # サマリーは1日1行なのでappend_rowsで1行書き込み
        ws.append_rows([row], value_input_option="USER_ENTERED")

    def append_log(self, log: dict):
        """scrape_logシートにログを追加"""
        ws = self.spreadsheet.worksheet(self.SHEET_SCRAPE_LOG)
        row = [
            datetime.now().isoformat(),
            log["target_date"],
            log["status"],
            log.get("units_count", 0),
            log.get("error_message", ""),
            log.get("duration_sec", 0),
        ]
        ws.append_rows([row], value_input_option="USER_ENTERED")

    def sort_daily_data_by_date(self):
        """daily_dataシートをplay_date（A列）昇順にソートする"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_DATA)
        # range省略でシート全体をソート（行数上限を超えても確実に動作）
        ws.sort((1, "asc"))
        logger.info("daily_data: 日付昇順ソート完了")

    # daily_data シートの列順（ヘッダー行がなくても動作させる）
    DAILY_COLUMNS = [
        "play_date", "machine_name", "unit_number",
        "total_games", "bb_count", "rb_count",
        "combined_prob", "bb_prob", "rb_prob",
        "estimated_setting", "setting_confidence",
        "estimated_diff", "day_of_week", "unit_suffix",
        "payout_rate", "store_name",
    ]

    def read_all_daily_data(self):
        """daily_dataの全データをリストのリストとして取得"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_DATA)
        rows = ws.get_all_values()
        if not rows:
            return []
        # 1行目がヘッダーかデータかを判定（play_date列が日付形式ならデータ行）
        first = rows[0]
        if first and len(first) > 0 and first[0] not in self.DAILY_COLUMNS and "日付" not in first[0]:
            # ヘッダー行なし: 全行がデータ
            data_rows = rows
        else:
            # ヘッダー行あり: 1行目をスキップ
            data_rows = rows[1:]
        records = []
        for row in data_rows:
            # 列数を合わせる（足りない場合は空文字で埋める）
            row += [""] * (len(self.DAILY_COLUMNS) - len(row))
            records.append(dict(zip(self.DAILY_COLUMNS, row)))
        return records

    def read_all_summary(self):
        """daily_summaryの全データを取得"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_SUMMARY)
        return ws.get_all_records()
