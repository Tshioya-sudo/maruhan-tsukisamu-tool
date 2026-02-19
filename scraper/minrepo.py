"""
みんレポスクレイピング本体。
Playwrightでマルハン月寒店のデータを取得する。

HTML構造（2026/2/17 WebFetch確認済み）:
- サーバーサイドレンダリング（WordPress）
- 機種別テーブル: 9列（台番|差枚|G数|出率|BB|RB|合成|BB率|RB率）
- 15行ごとにヘッダー行が再挿入される
- 最終行は<tr class="avg_row">
"""
from playwright.sync_api import sync_playwright
import urllib.parse
import time
import logging
import unicodedata

from scraper.parser import (
    parse_int,
    parse_prob,
    parse_payout_rate,
    parse_date_text,
    extract_article_id,
    extract_kishu_name,
)

logger = logging.getLogger(__name__)

# ページ読み込みタイムアウト（ms）
PAGE_TIMEOUT = 60000
# 要素待機タイムアウト（ms）
SELECTOR_TIMEOUT = 15000


class MinRepoScraper:
    BASE_URL = "https://min-repo.com"
    STORE_PATH = "/tag/%E3%83%9E%E3%83%AB%E3%83%8F%E3%83%B3%E6%9C%88%E5%AF%92%E5%BA%97/"
    SLEEP_SEC = 3  # リクエスト間隔（サーバー負荷配慮・GitHub Actions安定化）
    MAX_RETRY = 3

    # ブラウザUser-Agent（Bot検出対策）
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Phase 1 取得対象機種
    TARGET_MACHINES = [
        "マイジャグラーV",
        "スマスロ 沖ドキ!DUO アンコール",
        "ネオアイムジャグラーEX",
        "ゴーゴージャグラー３",
        "SアイムジャグラーＥＸ",
        "ウルトラミラクルジャグラー",
    ]

    def __init__(self, headless=True):
        self.headless = headless

    def _goto_with_retry(self, page, url, retries=3):
        """ページ遷移をリトライ付きで実行。domcontentloaded で待機。"""
        for attempt in range(retries):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                time.sleep(self.SLEEP_SEC)
                return True
            except Exception as e:
                logger.warning(f"ページ読み込みリトライ {attempt + 1}/{retries}: {url} - {e}")
                time.sleep(self.SLEEP_SEC * 2)
        logger.error(f"ページ読み込み失敗: {url}")
        return False

    def scrape_date_list(self) -> list[dict]:
        """店舗トップページから日付一覧を取得する。"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(user_agent=self.USER_AGENT)
            page = context.new_page()
            try:
                url = f"{self.BASE_URL}{self.STORE_PATH}"
                if not self._goto_with_retry(page, url):
                    return []

                # テーブル描画待機
                try:
                    page.wait_for_selector("div.table_wrap table", timeout=SELECTOR_TIMEOUT)
                except Exception:
                    logger.warning("店舗トップのテーブルが見つかりません")

                dates = []
                tables = page.query_selector_all("div.table_wrap table")
                for table in tables:
                    rows = table.query_selector_all("tr")
                    for row in rows:
                        ths = row.query_selector_all("th")
                        if ths:
                            continue

                        cells = row.query_selector_all("td")
                        if not cells or len(cells) < 4:
                            continue

                        link = cells[0].query_selector("a")
                        if not link:
                            continue

                        date_text = link.inner_text().strip()
                        href = link.get_attribute("href") or ""
                        article_id = extract_article_id(href)
                        avg_g = parse_int(cells[3].inner_text())

                        if article_id:
                            iso_date = parse_date_text(date_text)
                            dates.append({
                                "date": iso_date,
                                "date_text": date_text,
                                "article_id": article_id,
                                "avg_games": avg_g,
                            })

                logger.info(f"店舗トップ: {len(dates)}日分の日付を取得")
                return dates
            finally:
                browser.close()

    def scrape_machine_list(self, article_id: str) -> list[str]:
        """日付ページから利用可能な機種名一覧を取得する。"""
        url = f"{self.BASE_URL}/{article_id}/"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(user_agent=self.USER_AGENT)
            page = context.new_page()
            try:
                if not self._goto_with_retry(page, url):
                    return []

                machines = []
                links = page.query_selector_all("a[href*='kishu=']")
                for link in links:
                    href = link.get_attribute("href") or ""
                    name = extract_kishu_name(href)
                    if name and name not in machines:
                        machines.append(name)

                logger.info(f"記事{article_id}: {len(machines)}機種検出: {machines}")
                return machines
            finally:
                browser.close()

    def get_verified_machine_names(self, article_id: str) -> list[str]:
        """TARGET_MACHINESとみんレポの実際の表記を照合する。"""
        actual_names = self.scrape_machine_list(article_id)
        verified = []
        for target in self.TARGET_MACHINES:
            if target in actual_names:
                verified.append(target)
            else:
                matches = [a for a in actual_names
                           if self._normalize(target) in self._normalize(a)]
                if matches:
                    logger.warning(f"機種名修正: '{target}' → '{matches[0]}'")
                    verified.append(matches[0])
                else:
                    logger.error(f"機種未検出: '{target}'")
        return verified

    def check_machine_changes(self, article_id: str):
        """機種リストの変動を検出してログに記録"""
        actual = set(self.scrape_machine_list(article_id))
        target = set(self.TARGET_MACHINES)

        missing = target - actual
        if missing:
            logger.warning(f"[機種変動] TARGET_MACHINESにあるがみんレポにない: {missing}")

        juggler_keywords = ["ジャグラー", "アイム", "ゴーゴー", "ファンキー", "ミラクル", "ハッピー"]
        new_jugglers = [m for m in (actual - target)
                        if any(kw in m for kw in juggler_keywords)]
        if new_jugglers:
            logger.warning(f"[新機種検出] 未登録のジャグラー系: {new_jugglers}")

    def _scrape_machine_data_with_page(self, page, article_id: str,
                                       machine_name: str, target_date: str) -> list[dict]:
        """既存のpageオブジェクトを使って機種データを取得する（ブラウザ再利用用）"""
        encoded_name = urllib.parse.quote_plus(machine_name, encoding="utf-8")
        url = f"{self.BASE_URL}/{article_id}/?kishu={encoded_name}"

        if not self._goto_with_retry(page, url, retries=2):
            return []

        # テーブル描画待機
        try:
            page.wait_for_selector("table", timeout=SELECTOR_TIMEOUT)
        except Exception:
            logger.warning(f"テーブル要素が見つかりません: {machine_name}")

        header_check = page.query_selector(
            "th:has-text('台番'), td:has-text('台番')"
        )
        if not header_check:
            logger.warning(
                f"データテーブルのヘッダーが見つかりません: {machine_name}"
            )

        data = []
        tables = page.query_selector_all("div.table_wrap table")
        for table in tables:
            first_row = table.query_selector("tr")
            if not first_row:
                continue
            headers = [el.inner_text().strip()
                       for el in first_row.query_selector_all("th, td")]
            if not any("台番" in h for h in headers):
                continue

            rows = table.query_selector_all("tr")
            for row in rows:
                if row.query_selector("th"):
                    continue
                row_class = row.get_attribute("class") or ""
                if "avg_row" in row_class:
                    continue

                cells = row.query_selector_all("td")
                if len(cells) < 9:
                    continue

                unit_text = cells[0].inner_text().strip()
                unit_num = parse_int(unit_text)
                if unit_num is None:
                    continue

                data.append({
                    "play_date": target_date,
                    "machine_name": machine_name,
                    "unit_number": unit_num,
                    "diff_medals": parse_int(cells[1].inner_text()),
                    "total_games": parse_int(cells[2].inner_text()),
                    "payout_rate": parse_payout_rate(cells[3].inner_text()),
                    "bb_count": parse_int(cells[4].inner_text()),
                    "rb_count": parse_int(cells[5].inner_text()),
                    "combined_prob": parse_prob(cells[6].inner_text()),
                    "bb_prob": parse_prob(cells[7].inner_text()),
                    "rb_prob": parse_prob(cells[8].inner_text()),
                })

        logger.info(f"{target_date} {machine_name}: {len(data)}台")
        return data

    def scrape_machine_data(self, article_id: str, machine_name: str,
                            target_date: str) -> list[dict]:
        """特定日付・特定機種の全台データを取得する。"""
        for attempt in range(self.MAX_RETRY):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(user_agent=self.USER_AGENT)
                    page = context.new_page()
                    try:
                        return self._scrape_machine_data_with_page(
                            page, article_id, machine_name, target_date
                        )
                    finally:
                        browser.close()

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{self.MAX_RETRY}: {e}")
                time.sleep(self.SLEEP_SEC * 2)

        logger.error(f"{target_date} {machine_name}: 全リトライ失敗")
        return []

    def scrape_daily_all_machines(self, article_id: str, target_date: str,
                                  machines: list[str] = None) -> list[dict]:
        """特定日付の全対象機種データを一括取得する（単一ブラウザで全機種を処理）"""
        if machines is None:
            machines = self.TARGET_MACHINES

        all_data = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(user_agent=self.USER_AGENT)
            page = context.new_page()
            try:
                for machine in machines:
                    for attempt in range(self.MAX_RETRY):
                        try:
                            data = self._scrape_machine_data_with_page(
                                page, article_id, machine, target_date
                            )
                            all_data.extend(data)
                            time.sleep(self.SLEEP_SEC)
                            break
                        except Exception as e:
                            logger.warning(
                                f"Attempt {attempt + 1}/{self.MAX_RETRY} ({machine}): {e}"
                            )
                            time.sleep(self.SLEEP_SEC * 2)
                    else:
                        logger.error(f"{target_date} {machine}: 全リトライ失敗")
            finally:
                browser.close()

        logger.info(f"{target_date}: 合計 {len(all_data)}台 ({len(machines)}機種)")
        return all_data

    @staticmethod
    def _normalize(text: str) -> str:
        """全角→半角変換（マッチング用）"""
        return unicodedata.normalize("NFKC", text)
