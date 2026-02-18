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
        """GitHub Secrets またはローカルファイルから認証"""
        creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
        if creds_json:
            # GitHub Actions環境
            creds_dict = json.loads(creds_json)
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=self.SCOPES
            )
        else:
            # ローカル開発環境
            creds_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config",
                "credentials.json",
            )
            creds = Credentials.from_service_account_file(creds_path, scopes=self.SCOPES)

        self.client = gspread.authorize(creds)
        self.spreadsheet_id = os.environ.get("SPREADSHEET_ID", "")
        self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
        logger.info("Google Sheets接続成功")

    def get_existing_dates(self) -> set[str]:
        """既に取得済みの日付一覧を返す"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_DATA)
        dates = ws.col_values(1)[1:]  # ヘッダー除く
        return set(dates)

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

    def read_all_daily_data(self):
        """daily_dataの全データをリストのリストとして取得"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_DATA)
        return ws.get_all_records()

    def read_all_summary(self):
        """daily_summaryの全データを取得"""
        ws = self.spreadsheet.worksheet(self.SHEET_DAILY_SUMMARY)
        return ws.get_all_records()
