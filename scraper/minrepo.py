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
    parse_date_text,
    extract_article_id,
    extract_kishu_name,
)

logger = logging.getLogger(__name__)


class MinRepoScraper:
    BASE_URL = "https://min-repo.com"
    STORE_PATH = "/tag/%E3%83%9E%E3%83%AB%E3%83%8F%E3%83%B3%E6%9C%88%E5%AF%92%E5%BA%97/"
    SLEEP_SEC = 2  # リクエスト間隔（サーバー負荷配慮）
    MAX_RETRY = 3

    # ブラウザUser-Agent（Bot検出対策）
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Phase 1 取得対象機種
    # みんレポ上の正確な表記（2026/2/16 スクリーンショットで確認済み）
    TARGET_MACHINES = [
        "マイジャグラーV",                      # 40台 ← 半角V
        "スマスロ 沖ドキ!DUO アンコール",       # 36台
        "ネオアイムジャグラーEX",                # 24台 ← 半角EX
        "ゴーゴージャグラー３",                  # 22台 ← 全角３
        "SアイムジャグラーＥＸ",                 # 12台 ← 全角ＥＸ
        "ウルトラミラクルジャグラー",             # 6台
    ]

    def __init__(self, headless=True):
        self.headless = headless

    def _launch_browser(self, playwright):
        """User-Agent付きでブラウザとコンテキストを起動"""
        browser = playwright.chromium.launch(headless=self.headless)
        context = browser.new_context(user_agent=self.USER_AGENT)
        page = context.new_page()
        return browser, context, page

    def scrape_date_list(self) -> list[dict]:
        """
        店舗トップページから日付一覧を取得する。

        実際のHTML構造:
        <div class="table_wrap">
          <table>
            <tr><th>日付</th><th>総差枚</th><th>平均差枚</th><th>平均G</th><th>機種・末尾</th></tr>
            <tr>
              <td><a href="https://min-repo.com/2924707/">2/16(月)</a></td>
              <td>-</td><td>-</td><td>2,595</td><td>...</td>
            </tr>
          </table>
        </div>

        Returns:
            list[dict]: [{"date": "2026-02-16", "date_text": "2/16(月)",
                          "article_id": "2924707", "avg_games": 2595}, ...]
        """
        with sync_playwright() as p:
            browser, context, page = self._launch_browser(p)
            try:
                url = f"{self.BASE_URL}{self.STORE_PATH}"
                page.goto(url, wait_until="networkidle")
                time.sleep(self.SLEEP_SEC)

                # テーブル描画待機
                try:
                    page.wait_for_selector("div.table_wrap table", timeout=10000)
                except Exception:
                    logger.warning("店舗トップのテーブルが10秒以内に見つかりません")

                dates = []
                # table_wrap内のテーブルを取得
                tables = page.query_selector_all("div.table_wrap table")
                for table in tables:
                    rows = table.query_selector_all("tr")
                    for row in rows:
                        # ヘッダー行はスキップ
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
                        # 平均G数は4列目（index 3）
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
        """
        日付ページから利用可能な機種名一覧を取得する。

        実際のHTML構造:
        <table class="kishu">
          <tr>
            <td><a href="?kishu=%E3%83%9E%E3%82%A4...">マイジャグラーV</a> (40)</td>
            ...
          </tr>
        </table>

        Returns:
            list[str]: ["マイジャグラーV", "ゴーゴージャグラー３", ...]
        """
        url = f"{self.BASE_URL}/{article_id}/"
        with sync_playwright() as p:
            browser, context, page = self._launch_browser(p)
            try:
                page.goto(url, wait_until="networkidle")
                time.sleep(self.SLEEP_SEC)

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
        """
        初回実行時の安全策。
        日付ページの実際の?kishu=リンクから正確な機種名を取得し、
        TARGET_MACHINESとのマッチングを行う。
        """
        actual_names = self.scrape_machine_list(article_id)
        verified = []
        for target in self.TARGET_MACHINES:
            if target in actual_names:
                verified.append(target)
            else:
                # NFKC正規化で部分一致フォールバック
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

        # TARGET_MACHINESにあるがみんレポにない（撤去の可能性）
        missing = target - actual
        if missing:
            logger.warning(f"[機種変動] TARGET_MACHINESにあるがみんレポにない: {missing}")

        # みんレポにあるがTARGET_MACHINESにないジャグラー系（新台の可能性）
        juggler_keywords = ["ジャグラー", "アイム", "ゴーゴー", "ファンキー", "ミラクル", "ハッピー"]
        new_jugglers = [m for m in (actual - target)
                        if any(kw in m for kw in juggler_keywords)]
        if new_jugglers:
            logger.warning(f"[新機種検出] 未登録のジャグラー系: {new_jugglers}")

    def scrape_machine_data(self, article_id: str, machine_name: str,
                            target_date: str) -> list[dict]:
        """
        特定日付・特定機種の全台データを取得する。

        実際のHTML構造（9列）:
        <table> (classなし、div.table_wrap内)
          <tr><th>台番</th><th>差枚</th><th>G数</th><th>出率</th>
              <th>BB</th><th>RB</th><th>合成</th><th>BB率</th><th>RB率</th></tr>
          <tr>
            <td><a href="...?num=565">565</a></td>
            <td>0</td><td>5,743</td><td>100%</td>
            <td>26</td><td>23</td><td>1/117</td><td>1/221</td><td>1/250</td>
          </tr>
          ... (15行ごとにヘッダー行が再挿入される)
          <tr class="avg_row">...</tr>  ← 最終行は平均
        </table>
        """
        encoded_name = urllib.parse.quote_plus(machine_name, encoding="utf-8")
        url = f"{self.BASE_URL}/{article_id}/?kishu={encoded_name}"

        for attempt in range(self.MAX_RETRY):
            try:
                with sync_playwright() as p:
                    browser, context, page = self._launch_browser(p)
                    try:
                        page.goto(url, wait_until="networkidle")
                        time.sleep(self.SLEEP_SEC)

                        # テーブル描画待機
                        try:
                            page.wait_for_selector("table", timeout=10000)
                        except Exception:
                            logger.warning(f"テーブル要素が10秒以内に見つかりません: {machine_name}")

                        # 「台番」ヘッダーを含むテーブルを探す
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
                            # ヘッダー行で「台番」を含むテーブルを特定
                            first_row = table.query_selector("tr")
                            if not first_row:
                                continue
                            headers = [el.inner_text().strip()
                                       for el in first_row.query_selector_all("th, td")]
                            if not any("台番" in h for h in headers):
                                continue

                            rows = table.query_selector_all("tr")
                            for row in rows:
                                # ヘッダー行（th含む）はスキップ
                                if row.query_selector("th"):
                                    continue
                                # 平均行はスキップ
                                row_class = row.get_attribute("class") or ""
                                if "avg_row" in row_class:
                                    continue

                                cells = row.query_selector_all("td")
                                if len(cells) < 9:
                                    continue

                                # 列マッピング（実際の9列構造）:
                                # 0:台番 1:差枚 2:G数 3:出率 4:BB 5:RB 6:合成 7:BB率 8:RB率
                                unit_text = cells[0].inner_text().strip()
                                unit_num = parse_int(unit_text)
                                if unit_num is None:
                                    continue

                                data.append({
                                    "play_date": target_date,
                                    "machine_name": machine_name,
                                    "unit_number": unit_num,
                                    "total_games": parse_int(cells[2].inner_text()),
                                    "bb_count": parse_int(cells[4].inner_text()),
                                    "rb_count": parse_int(cells[5].inner_text()),
                                    "combined_prob": parse_prob(cells[6].inner_text()),
                                    "bb_prob": parse_prob(cells[7].inner_text()),
                                    "rb_prob": parse_prob(cells[8].inner_text()),
                                })

                        logger.info(f"{target_date} {machine_name}: {len(data)}台")
                        return data
                    finally:
                        browser.close()

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{self.MAX_RETRY}: {e}")
                time.sleep(self.SLEEP_SEC * 2)

        logger.error(f"{target_date} {machine_name}: 全リトライ失敗")
        return []

    def scrape_daily_all_machines(self, article_id: str, target_date: str,
                                  machines: list[str] = None) -> list[dict]:
        """特定日付の全対象機種データを一括取得する。"""
        if machines is None:
            machines = self.TARGET_MACHINES

        all_data = []
        for machine in machines:
            data = self.scrape_machine_data(article_id, machine, target_date)
            all_data.extend(data)
            time.sleep(self.SLEEP_SEC)

        logger.info(f"{target_date}: 合計 {len(all_data)}台 ({len(machines)}機種)")
        return all_data

    @staticmethod
    def _normalize(text: str) -> str:
        """全角→半角変換（マッチング用）"""
        return unicodedata.normalize("NFKC", text)
